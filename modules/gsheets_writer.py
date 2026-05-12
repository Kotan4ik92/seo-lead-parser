"""
Push scan results to Google Sheets.
Each scan creates a new tab: "MM-DD HH:MM | query[:25]"

Requires in st.secrets:
  [gcp_service_account]  — service account JSON as TOML dict
  GSHEET_ID              — target spreadsheet ID
"""

import datetime

import gspread
from google.oauth2.service_account import Credentials

from modules.sheets_writer import HEADERS, _row_data

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Dark-blue header color (matches Excel)
_HEADER_BG  = {"red": 0.122, "green": 0.220, "blue": 0.392}
_HEADER_FG  = {"red": 1.0,   "green": 1.0,   "blue": 1.0}

# Temperature color map  (R, G, B) as 0–1 floats
_TEMP_COLOR = {
    "💥": (0.753, 0.0,   0.0  ),   # critical red
    "🔥": (0.886, 0.420, 0.039),   # hot orange
    "🌤": (0.965, 0.757, 0.259),   # warm yellow
    "❄️": (0.271, 0.447, 0.769),   # cold blue
    "⛔": (0.502, 0.502, 0.502),   # dead grey
}


def _gc(sa_info: dict) -> gspread.Client:
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)


def _score_text(v) -> str:
    if isinstance(v, int):
        return f"{v}/10" if v >= 0 else "n/a"
    return str(v) if v is not None else "n/a"


def push_to_gsheets(
    results: list[tuple],
    query: str,
    sa_info: dict,
    spreadsheet_id: str,
) -> str:
    """
    Writes results to a new tab.  Returns the tab URL.
    Raises gspread.exceptions.* on auth / API errors.
    """
    gc = _gc(sa_info)
    sh = gc.open_by_key(spreadsheet_id)

    # Tab name: "05-12 14:30 | boutique hotel"
    tab_name = datetime.datetime.now().strftime("%m-%d %H:%M") + " | " + query[:25]
    existing = {ws.title for ws in sh.worksheets()}
    if tab_name in existing:
        tab_name += "_2"

    n_rows = max(len(results) + 10, 50)
    ws = sh.add_worksheet(title=tab_name, rows=n_rows, cols=len(HEADERS))

    # ── Build rows ──────────────────────────────────────────────────────────────
    AI_COLS = {6, 8, 10, 11, 12}   # 0-based indices of AI score columns

    rows: list[list] = [HEADERS]
    for i, (seo, sc, temp) in enumerate(results, 1):
        row = _row_data(i, seo, sc, temp, query)
        for ci in AI_COLS:
            row[ci] = _score_text(row[ci])
        rows.append(row)

    # Summary footer
    hot  = sum(1 for _, s, _ in results if s >= 45)
    warm = sum(1 for _, s, _ in results if 20 <= s < 45)
    cold = sum(1 for r, s, _ in results if s < 20 and r.reachable)
    rows.append([])
    rows.append([
        f"Total: {len(results)} sites  |  💥🔥 {hot} hot  |  🌤 {warm} warm  |  ❄️ {cold} cold"
    ])

    ws.update("A1", rows, value_input_option="USER_ENTERED")

    # ── Formatting via batchUpdate ───────────────────────────────────────────────
    sid = ws.id
    requests = []

    # Freeze header row
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sid,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Bold blue header row
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": _HEADER_BG,
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": _HEADER_FG,
                        "fontSize": 10,
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }
    })

    # Color temperature column (col index 3, 0-based) per row
    for row_i, (_, sc, temp) in enumerate(results, 1):   # row 0 = header
        first = temp[:1] if temp else ""
        rgb = _TEMP_COLOR.get(first)
        if rgb:
            r, g, b = rgb
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": row_i,
                        "endRowIndex": row_i + 1,
                        "startColumnIndex": 3,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": r, "green": g, "blue": b},
                            "textFormat": {"bold": True, "foregroundColor": _HEADER_FG},
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            })

    # Auto-resize all columns
    requests.append({
        "autoResizeDimensions": {
            "dimensions": {
                "sheetId": sid,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": len(HEADERS),
            }
        }
    })

    sh.batch_update({"requests": requests})

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sid}"
