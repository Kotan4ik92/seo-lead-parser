"""
SQLite persistence layer — replaces all JSON files in data/.

Tables:
  leads       — url, status, contacted_at, contact_count, note
  scan_history — scan run records (last 100)
  sent_emails  — deduplication of outreach
  send_log     — daily send counter
"""

import datetime
import json
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path("data") / "leads.db"

_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(exist_ok=True)
        con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.row_factory = sqlite3.Row
        _local.conn = con
        _init_schema(con)
    return _local.conn


def _init_schema(con: sqlite3.Connection):
    con.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            url           TEXT PRIMARY KEY,
            status        TEXT NOT NULL DEFAULT '🟡 New',
            contacted_at  TEXT,
            contact_count INTEGER NOT NULL DEFAULT 0,
            note          TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS scan_history (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            date  TEXT NOT NULL,
            query TEXT NOT NULL,
            geo   TEXT NOT NULL,
            niche TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            hot   INTEGER NOT NULL DEFAULT 0,
            fire  INTEGER NOT NULL DEFAULT 0,
            warm  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sent_emails (
            email TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS send_log (
            date  TEXT PRIMARY KEY,
            count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS email_tracking (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_url   TEXT NOT NULL,
            to_email   TEXT NOT NULL,
            subject    TEXT NOT NULL,
            sent_at    TEXT NOT NULL,
            utm_content TEXT NOT NULL
        );
    """)
    con.commit()


# ── Leads / statuses ──────────────────────────────────────────────────────────

def get_all_statuses() -> dict:
    rows = _conn().execute("SELECT url, status FROM leads").fetchall()
    return {r["url"]: r["status"] for r in rows}


def save_status(url: str, status: str):
    con = _conn()
    con.execute(
        "INSERT INTO leads (url, status) VALUES (?, ?) "
        "ON CONFLICT(url) DO UPDATE SET status = excluded.status",
        (url, status),
    )
    con.commit()


# ── Lead data (contacted_at, contact_count, note) ─────────────────────────────

def get_all_lead_data() -> dict:
    rows = _conn().execute(
        "SELECT url, contacted_at, contact_count, note FROM leads"
    ).fetchall()
    result = {}
    for r in rows:
        entry = {}
        if r["contacted_at"]:
            entry["contacted_at"] = r["contacted_at"]
        if r["contact_count"]:
            entry["contact_count"] = r["contact_count"]
        if r["note"]:
            entry["note"] = r["note"]
        if entry:
            result[r["url"]] = entry
    return result


def mark_contacted(url: str):
    today = datetime.date.today().isoformat()
    con = _conn()
    con.execute(
        "INSERT INTO leads (url, contacted_at, contact_count) VALUES (?, ?, 1) "
        "ON CONFLICT(url) DO UPDATE SET "
        "  contacted_at  = excluded.contacted_at, "
        "  contact_count = contact_count + 1",
        (url, today),
    )
    con.commit()


def save_note(url: str, note: str):
    con = _conn()
    con.execute(
        "INSERT INTO leads (url, note) VALUES (?, ?) "
        "ON CONFLICT(url) DO UPDATE SET note = excluded.note",
        (url, note),
    )
    con.commit()


def get_followup_due(days: int = 7) -> list[tuple[str, int]]:
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    today  = datetime.date.today()
    rows = _conn().execute(
        "SELECT url, contacted_at FROM leads "
        "WHERE status = '📨 Contacted' AND contacted_at IS NOT NULL AND contacted_at <= ?",
        (cutoff,),
    ).fetchall()
    result = []
    for r in rows:
        delta = (today - datetime.date.fromisoformat(r["contacted_at"])).days
        result.append((r["url"], delta))
    return result


# ── Scan history ──────────────────────────────────────────────────────────────

def get_history() -> list:
    rows = _conn().execute(
        "SELECT date, query, geo, niche, total, hot, fire, warm "
        "FROM scan_history ORDER BY id DESC LIMIT 100"
    ).fetchall()
    return [dict(r) for r in rows]


def append_history(query: str, geo: str, niche: str,
                   total: int, hot: int, fire: int, warm: int):
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    con = _conn()
    con.execute(
        "INSERT INTO scan_history (date, query, geo, niche, total, hot, fire, warm) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (date, query, geo, niche, total, hot, fire, warm),
    )
    # Keep only last 100 records
    con.execute(
        "DELETE FROM scan_history WHERE id NOT IN "
        "(SELECT id FROM scan_history ORDER BY id DESC LIMIT 100)"
    )
    con.commit()


# ── Sent emails ───────────────────────────────────────────────────────────────

def get_sent_emails() -> set:
    rows = _conn().execute("SELECT email FROM sent_emails").fetchall()
    return {r["email"] for r in rows}


def save_sent_email(email: str):
    con = _conn()
    con.execute(
        "INSERT OR IGNORE INTO sent_emails (email) VALUES (?)",
        (email.lower().strip(),),
    )
    con.commit()


# ── Daily send counter ────────────────────────────────────────────────────────

def get_today_send_count() -> int:
    today = datetime.date.today().isoformat()
    row = _conn().execute(
        "SELECT count FROM send_log WHERE date = ?", (today,)
    ).fetchone()
    return row["count"] if row else 0


def increment_send_count():
    today = datetime.date.today().isoformat()
    con = _conn()
    con.execute(
        "INSERT INTO send_log (date, count) VALUES (?, 1) "
        "ON CONFLICT(date) DO UPDATE SET count = count + 1",
        (today,),
    )
    con.commit()


# ── Migration from JSON files ─────────────────────────────────────────────────

def migrate_from_json():
    """One-time import of existing JSON data into SQLite. Safe to call repeatedly."""
    data_dir = Path("data")
    con = _conn()

    statuses_file = data_dir / "statuses.json"
    if statuses_file.exists():
        try:
            statuses = json.loads(statuses_file.read_text(encoding="utf-8"))
            for url, status in statuses.items():
                con.execute(
                    "INSERT INTO leads (url, status) VALUES (?, ?) "
                    "ON CONFLICT(url) DO UPDATE SET status = excluded.status",
                    (url, status),
                )
        except Exception:
            pass

    lead_data_file = data_dir / "lead_data.json"
    if lead_data_file.exists():
        try:
            lead_data = json.loads(lead_data_file.read_text(encoding="utf-8"))
            for url, entry in lead_data.items():
                con.execute(
                    "INSERT INTO leads (url, contacted_at, contact_count, note) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(url) DO UPDATE SET "
                    "  contacted_at  = COALESCE(excluded.contacted_at, contacted_at), "
                    "  contact_count = COALESCE(excluded.contact_count, contact_count), "
                    "  note          = COALESCE(excluded.note, note)",
                    (
                        url,
                        entry.get("contacted_at"),
                        entry.get("contact_count", 0),
                        entry.get("note", ""),
                    ),
                )
        except Exception:
            pass

    history_file = data_dir / "history.json"
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
            existing_count = con.execute("SELECT COUNT(*) FROM scan_history").fetchone()[0]
            if existing_count == 0:
                for h in reversed(history):
                    con.execute(
                        "INSERT INTO scan_history (date, query, geo, niche, total, hot, fire, warm) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (h.get("date", ""), h.get("query", ""), h.get("geo", ""),
                         h.get("niche", ""), h.get("total", 0), h.get("hot", 0),
                         h.get("fire", 0), h.get("warm", 0)),
                    )
        except Exception:
            pass

    sent_file = data_dir / "sent_emails.json"
    if sent_file.exists():
        try:
            sent = json.loads(sent_file.read_text(encoding="utf-8"))
            for email in sent:
                con.execute(
                    "INSERT OR IGNORE INTO sent_emails (email) VALUES (?)",
                    (email.lower().strip(),),
                )
        except Exception:
            pass

    send_log_file = data_dir / "send_log.json"
    if send_log_file.exists():
        try:
            log = json.loads(send_log_file.read_text(encoding="utf-8"))
            for date, count in log.items():
                con.execute(
                    "INSERT INTO send_log (date, count) VALUES (?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET count = MAX(count, excluded.count)",
                    (date, count),
                )
        except Exception:
            pass

    con.commit()


# ── Email tracking ────────────────────────────────────────────────────────────

def record_email_sent(lead_url: str, to_email: str, subject: str, utm_content: str):
    sent_at = datetime.datetime.now().isoformat(timespec="seconds")
    con = _conn()
    con.execute(
        "INSERT INTO email_tracking (lead_url, to_email, subject, sent_at, utm_content) "
        "VALUES (?, ?, ?, ?, ?)",
        (lead_url, to_email.lower().strip(), subject, sent_at, utm_content),
    )
    con.commit()


def get_email_tracking_stats() -> list[dict]:
    rows = _conn().execute(
        "SELECT lead_url, to_email, subject, sent_at, utm_content "
        "FROM email_tracking ORDER BY id DESC LIMIT 500"
    ).fetchall()
    return [dict(r) for r in rows]
