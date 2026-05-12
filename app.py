"""
SEO Lead Parser — Streamlit Web App
Запуск локально : streamlit run app.py
Деплой         : Streamlit Community Cloud (github.com → connect repo)
"""

import io
import json
import time
import random
import datetime
import requests
from pathlib import Path

import streamlit as st

import config

# ── Persistent storage ────────────────────────────────────────────────────────
DATA_DIR      = Path("data")
DATA_DIR.mkdir(exist_ok=True)
STATUSES_FILE   = DATA_DIR / "statuses.json"
HISTORY_FILE    = DATA_DIR / "history.json"
SENT_EMAILS_FILE = DATA_DIR / "sent_emails.json"

STATUS_OPTIONS = ["🟡 New", "📨 Contacted", "✅ Interested", "❌ Skip"]

def load_statuses() -> dict:
    try:
        return json.loads(STATUSES_FILE.read_text(encoding="utf-8")) if STATUSES_FILE.exists() else {}
    except Exception:
        return {}

def save_status(url: str, status: str):
    s = load_statuses()
    s[url] = status
    STATUSES_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

def load_history() -> list:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    except Exception:
        return []

def load_sent_emails() -> set:
    try:
        data = json.loads(SENT_EMAILS_FILE.read_text(encoding="utf-8")) if SENT_EMAILS_FILE.exists() else []
        return set(data)
    except Exception:
        return set()

def save_sent_email(email: str):
    sent = load_sent_emails()
    sent.add(email.lower().strip())
    SENT_EMAILS_FILE.write_text(json.dumps(sorted(sent), ensure_ascii=False, indent=2), encoding="utf-8")

def append_history(query: str, geo: str, niche: str, total: int, hot: int, fire: int, warm: int):
    h = load_history()
    h.insert(0, {
        "date":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "query": query, "geo": geo, "niche": niche,
        "total": total, "hot": hot, "fire": fire, "warm": warm,
    })
    HISTORY_FILE.write_text(json.dumps(h[:100], ensure_ascii=False, indent=2), encoding="utf-8")

# On Streamlit Cloud, secrets are injected via st.secrets
_GSHEET_SA:   dict | None = None   # service account JSON dict
_GSHEET_ID:   str  = ""            # spreadsheet ID

try:
    import streamlit as _st_pre
    if "SERPER_API_KEY" in _st_pre.secrets:
        config.SERPER_API_KEY = _st_pre.secrets["SERPER_API_KEY"]
    if "OPENAI_API_KEY" in _st_pre.secrets:
        config.OPENAI_API_KEY = _st_pre.secrets["OPENAI_API_KEY"]
    if "gcp_service_account" in _st_pre.secrets:
        _GSHEET_SA = dict(_st_pre.secrets["gcp_service_account"])
    if "GSHEET_ID" in _st_pre.secrets:
        _GSHEET_ID = _st_pre.secrets["GSHEET_ID"]
    if "ZOHO_EMAIL" in _st_pre.secrets:
        config.ZOHO_EMAIL = _st_pre.secrets["ZOHO_EMAIL"]
    if "ZOHO_APP_PASSWORD" in _st_pre.secrets:
        config.ZOHO_APP_PASSWORD = _st_pre.secrets["ZOHO_APP_PASSWORD"]
except Exception:
    pass

from modules.serp_scraper    import scrape_serp
from modules.seo_scanner     import scan
from modules.scorer          import score
from modules.contact_finder  import find_contacts
from modules.email_writer    import generate_email
from modules.sheets_writer   import write_to_excel
from modules.gsheets_writer  import push_to_gsheets
from modules.email_sender    import send_cold_email

# ── Constants ─────────────────────────────────────────────────────────────────

GEO_OPTIONS = {
    "USA":         "us",
    "UK":          "gb",
    "Canada":      "ca",
    "Australia":   "au",
    "New Zealand": "nz",
    "Ireland":     "ie",
    "Germany":     "de",
    "France":      "fr",
    "Netherlands": "nl",
    "Belgium":     "be",
    "Austria":     "at",
    "Switzerland": "ch",
    "Sweden":      "se",
    "Norway":      "no",
    "Denmark":     "dk",
    "Spain":       "es",
    "Italy":       "it",
    "Poland":      "pl",
    "Kazakhstan":  "kz",
}

LANG_OPTIONS = {
    "Any":        "",
    "English":    "lang_en",
    "German":     "lang_de",
    "French":     "lang_fr",
    "Spanish":    "lang_es",
    "Italian":    "lang_it",
    "Dutch":      "lang_nl",
    "Polish":     "lang_pl",
    "Swedish":    "lang_sv",
    "Norwegian":  "lang_no",
    "Danish":     "lang_da",
    "Portuguese": "lang_pt",
}

NICHE_OPTIONS  = [
    "All niches", "Ecommerce", "HoReCa", "SaaS",
    "Local Services", "Real Estate", "Healthcare",
    "Beauty & Wellness", "Travel & Tourism", "Fitness & Sport",
    "Education", "Legal & Finance",
]
NICHE_ICONS = {
    "All niches":       "🌐",
    "Ecommerce":        "🛒",
    "HoReCa":          "🍽️",
    "SaaS":            "💻",
    "Local Services":  "🔧",
    "Real Estate":     "🏠",
    "Healthcare":      "🏥",
    "Beauty & Wellness": "💅",
    "Travel & Tourism": "✈️",
    "Fitness & Sport": "🏋️",
    "Education":       "🎓",
    "Legal & Finance": "⚖️",
}

LANG_FLAGS = {
    "Any":        "",
    "English":    "gb",
    "German":     "de",
    "French":     "fr",
    "Spanish":    "es",
    "Italian":    "it",
    "Dutch":      "nl",
    "Polish":     "pl",
    "Swedish":    "se",
    "Norwegian":  "no",
    "Danish":     "dk",
    "Portuguese": "pt",
}

FALLBACK_TEMPLATES = [
    "online furniture store USA",
    "restaurant chain Chicago",
    "CRM software small business",
    "pet supplies store online UK",
    "boutique hotel New York",
    "accounting software SMB USA",
]


@st.cache_data(ttl=86400, show_spinner=False)
def get_ai_templates(openai_key: str, niche: str, geo: str, lang: str) -> list[str]:
    """Генерирует 6 актуальных запросов через GPT. Кеш 24ч."""
    if not openai_key:
        return FALLBACK_TEMPLATES
    niche_hint = f"Focus on {niche} niche only." if niche != "All niches" else \
                 "Mix of ecommerce, HoReCa (hotels/restaurants/cafes), and SaaS."
    geo_hint  = f"Target market: {geo}." if geo else "Target markets: USA, UK, Canada, Australia, EU."
    lang_hint = f"Queries should be in {lang} language." if lang and lang != "Any" else "Queries in English."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        today = datetime.date.today().strftime("%B %d, %Y")
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": f"""Today is {today}. {niche_hint} {geo_hint} {lang_hint}

Generate 6 short Google search queries (3-5 words each) that a person would type to find a specific TYPE of small/medium business.
Rules:
- Write like a real person searching for a business, NOT like an SEO audit query
- No words like "SEO", "ranking", "poor", "weak", "examples", dates or years
- Good examples: "online pet store UK", "boutique hotel Chicago", "HR software startup"
- Bad examples: "ecommerce sites spring 2026 UK poor SEO", "SaaS startups with low rankings"
- Keep each query under 6 words
- Match the target market and language specified above

Return ONLY a JSON array of 6 strings, no markdown:
["query 1", "query 2", "query 3", "query 4", "query 5", "query 6"]"""}],
            temperature=0.8,
            max_tokens=150,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        templates = json.loads(raw)
        if isinstance(templates, list) and len(templates) >= 6:
            return templates[:6]
    except Exception:
        pass
    return FALLBACK_TEMPLATES


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEO Lead Parser",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    # Keys are set via Streamlit Cloud Secrets — never shown in UI
    serper_key = config.SERPER_API_KEY
    openai_key = config.OPENAI_API_KEY
    serper_ok  = "✅" if serper_key else "❌ not set"
    openai_ok  = "✅" if openai_key else "❌ not set"
    gsheet_ok  = "✅" if (_GSHEET_SA and _GSHEET_ID) else "❌ not set"
    zoho_ok    = "✅" if (config.ZOHO_EMAIL and config.ZOHO_APP_PASSWORD) else "❌ not set"
    st.caption(f"Serper.dev API: {serper_ok}")
    st.caption(f"OpenAI API: {openai_ok}")
    st.caption(f"Google Sheets: {gsheet_ok}")
    st.caption(f"Zoho Mail: {zoho_ok}")
    if not serper_key or not openai_key:
        st.warning("API keys missing. Set them in Streamlit Cloud → App Settings → Secrets.", icon="🔑")

    st.divider()
    st.caption("**Search settings**")

    niche_col, niche_icon_col = st.columns([4, 1])
    with niche_col:
        niche = st.selectbox("Niche", NICHE_OPTIONS, index=0)
    with niche_icon_col:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:26px; line-height:1'>{NICHE_ICONS[niche]}</div>",
            unsafe_allow_html=True,
        )

    geo_col, flag_col = st.columns([4, 1])
    with geo_col:
        geo_label = st.selectbox("Market / Geo", list(GEO_OPTIONS.keys()), index=0)
    geo = GEO_OPTIONS[geo_label]
    with flag_col:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.markdown(
            f'<img src="https://flagcdn.com/w80/{geo}.png" '
            f'style="height:28px; border-radius:4px; box-shadow:0 1px 4px rgba(0,0,0,0.4)">',
            unsafe_allow_html=True,
        )

    lang_col, lang_icon_col = st.columns([4, 1])
    with lang_col:
        lang_label = st.selectbox("Site language", list(LANG_OPTIONS.keys()), index=0)
    lang_restrict = LANG_OPTIONS[lang_label]
    with lang_icon_col:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        lang_flag = LANG_FLAGS.get(lang_label, "")
        if lang_flag:
            st.markdown(
                f'<img src="https://flagcdn.com/w80/{lang_flag}.png" '
                f'style="height:28px; border-radius:4px; box-shadow:0 1px 4px rgba(0,0,0,0.4)">',
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<div style='font-size:26px; line-height:1'>🌐</div>",
                        unsafe_allow_html=True)

    max_results = st.slider("Max sites to scan", 5, 100, 30, step=5)
    max_pages   = st.slider("Pages per site (sitemap)", 5, 20, 15, step=5)

    st.divider()
    st.caption("**Lead filters**")

    score_min, score_max = st.slider(
        "Score range",
        min_value=0, max_value=100,
        value=(0, 100), step=5,
    )
    min_issues = st.slider("Min technical issues", 0, 10, 0, step=1,
                           help="Show only sites with at least N technical problems")

    st.divider()
    st.markdown("Made with ❤️ for SEO agencies")

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🔍 SEO Lead Parser")
st.markdown("Find websites with poor SEO → turn them into warm leads.")

# AI templates
tmpl_label_col, tmpl_refresh_col = st.columns([5, 1])
tmpl_label_col.caption("Quick templates (AI picks trending niches for today):")
if tmpl_refresh_col.button("🔄", help="Regenerate templates", use_container_width=True):
    get_ai_templates.clear()

TEMPLATES = get_ai_templates(config.OPENAI_API_KEY, niche, geo_label, lang_label)

tmpl_cols = st.columns(6)
for i, tmpl in enumerate(TEMPLATES):
    if tmpl_cols[i].button(tmpl, key=f"tmpl_{i}", use_container_width=True):
        st.session_state["query_input"] = tmpl

# Query input
col1, col2 = st.columns([4, 1])
with col1:
    query = st.text_input(
        "Search query",
        placeholder='e.g. "online furniture store USA"',
        label_visibility="collapsed",
        key="query_input",
    )
with col2:
    run_btn = st.button("🚀 Run", use_container_width=True, type="primary")

st.divider()

# ── Run pipeline ──────────────────────────────────────────────────────────────
if run_btn and query:
    # Clear previous results when starting a new scan
    for key in ["scan_results", "scan_query", "scan_excel"]:
        st.session_state.pop(key, None)

    config.SEARCH_GEO         = geo
    config.MAX_RESULTS        = max_results
    config.MAX_PAGES_PER_SITE = max_pages

    niche_tag = f" | Niche: {niche}" if niche != "All niches" else ""
    lang_tag  = f" | Lang: {lang_label}" if lang_restrict else ""
    st.info(f"Searching: **{query}** | Geo: {geo_label}{niche_tag}{lang_tag} | Up to {max_results} sites")

    # Step 1: SERP
    with st.spinner("🌐 Fetching search results…"):
        urls = scrape_serp(query, max_results=max_results,
                           lang_restrict=lang_restrict, niche=niche)

    if not urls:
        st.error("No URLs found. Check your Serper.dev API key or try a different query.")
        st.stop()

    st.success(f"Found **{len(urls)}** sites. Scanning SEO now…")

    # Step 2: Scan each site
    progress_bar = st.progress(0)
    status_text  = st.empty()

    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(config.USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    })

    all_results = []
    for i, url in enumerate(urls):
        status_text.markdown(f"**[{i+1}/{len(urls)}]** Scanning `{url}` …")
        seo = scan(url, session, query=query, niche=niche)
        lead_score, temp = score(seo)
        all_results.append((seo, lead_score, temp))
        progress_bar.progress((i + 1) / len(urls))
        time.sleep(config.REQUEST_DELAY + random.uniform(0, 0.5))

    status_text.empty()
    progress_bar.empty()

    all_results.sort(key=lambda x: x[1], reverse=True)

    # Save to session state so button clicks don't lose results
    st.session_state["scan_results"] = all_results
    st.session_state["scan_query"]   = query

    # Append to history
    _hot  = sum(1 for _, s, _ in all_results if s >= 70)
    _fire = sum(1 for _, s, _ in all_results if 45 <= s < 70)
    _warm = sum(1 for _, s, _ in all_results if 20 <= s < 45)
    append_history(query, geo_label, niche, len(all_results), _hot, _fire, _warm)

    # Pre-generate Excel bytes once
    safe_q   = query.replace(" ", "_").replace("/", "-")[:40]
    filename = f"leads_{safe_q}.xlsx"
    write_to_excel(all_results, query, filename=filename)
    with open(filename, "rb") as f:
        st.session_state["scan_excel"] = (f.read(), filename)

elif run_btn and not query:
    st.warning("Please enter a search query.")

# ── Show results (persisted in session_state) ─────────────────────────────────
if "scan_results" in st.session_state:
    all_results = st.session_state["scan_results"]
    saved_query = st.session_state.get("scan_query", "")

    filtered = [
        (seo, s, t) for seo, s, t in all_results
        if score_min <= s <= score_max
        and seo.issues_count >= min_issues
    ]

    # Stats
    hot  = sum(1 for _, s, _ in filtered if s >= 70)
    fire = sum(1 for _, s, _ in filtered if 45 <= s < 70)
    warm = sum(1 for _, s, _ in filtered if 20 <= s < 45)
    cold = sum(1 for _, s, _ in filtered if s < 20)
    dead = sum(1 for r, _, _ in filtered if not r.reachable)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💥 Critical", hot)
    c2.metric("🔥 Hot",      fire)
    c3.metric("🌤 Warm",     warm)
    c4.metric("❄️ Cold",    cold)
    c5.metric("⛔ Dead",     dead)

    st.divider()

    # Export buttons
    export_col1, export_col2 = st.columns([2, 3])

    if "scan_excel" in st.session_state:
        excel_bytes, filename = st.session_state["scan_excel"]
        export_col1.download_button(
            "📥 Download Excel",
            data=excel_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if _GSHEET_SA and _GSHEET_ID and "scan_results" in st.session_state:
        if export_col2.button("📊 Push to Google Sheets", use_container_width=True):
            with st.spinner("Pushing to Google Sheets…"):
                try:
                    sheet_url = push_to_gsheets(
                        results=st.session_state["scan_results"],
                        query=st.session_state.get("scan_query", "scan"),
                        sa_info=_GSHEET_SA,
                        spreadsheet_id=_GSHEET_ID,
                    )
                    st.success(f"✅ Done! [Open Google Sheets]({sheet_url})", icon="📊")
                except Exception as e:
                    st.error(f"Google Sheets error: {e}")

    # ── Auto-send emails ───────────────────────────────────────────────────────
    if config.ZOHO_EMAIL and config.ZOHO_APP_PASSWORD and "scan_results" in st.session_state:
        st.divider()
        st.markdown("**📤 Auto-send cold emails**")
        st.caption("Finds contacts → generates email → sends to all warm/hot leads (score 20+) with status 🟡 New")

        if st.button("📤 Send to all hot/warm leads", type="primary", use_container_width=False):
            all_res   = st.session_state["scan_results"]
            saved_q   = st.session_state.get("scan_query", "")
            statuses  = load_statuses()

            sent_emails = load_sent_emails()
            targets = [
                (seo, sc, t) for seo, sc, t in all_res
                if seo.reachable and sc >= 20
                and statuses.get(seo.url, "🟡 New") == "🟡 New"
            ]

            if not targets:
                st.info("No new warm/hot leads to send to — all already contacted or score < 20.")
            else:
                st.info(f"Found **{len(targets)}** leads to process. Starting…")
                prog   = st.progress(0)
                log    = st.empty()

                sent_ok, no_contact, errors = 0, 0, 0

                for i, (seo, sc, temp) in enumerate(targets):
                    log.markdown(f"**[{i+1}/{len(targets)}]** `{seo.url}` — finding contacts…")

                    # 1. Find contacts
                    contacts = find_contacts(seo.url)
                    emails   = contacts.get("emails", [])

                    if not emails:
                        no_contact += 1
                        prog.progress((i + 1) / len(targets))
                        continue

                    # Skip if this email was already contacted before
                    if emails[0].lower().strip() in sent_emails:
                        no_contact += 1
                        prog.progress((i + 1) / len(targets))
                        continue

                    # 2. Generate email
                    log.markdown(f"**[{i+1}/{len(targets)}]** `{seo.url}` — writing email…")
                    em = generate_email(
                        url=seo.url,
                        query=saved_q,
                        issues=seo.issues,
                        verdict=seo.ai.ai_verdict if seo.ai else "",
                        owner=contacts.get("owner", ""),
                        email=emails[0],
                    )

                    if em.get("error") or not em.get("body"):
                        errors += 1
                        st.warning(f"❌ `{seo.url}` → email gen error: {em.get('error', 'empty body')}")
                        prog.progress((i + 1) / len(targets))
                        continue

                    # 3. Send
                    log.markdown(f"**[{i+1}/{len(targets)}]** `{seo.url}` — sending to {emails[0]}…")
                    result = send_cold_email(
                        to_email=emails[0],
                        subject=em["subject"],
                        body=em["body"],
                        from_email=config.ZOHO_EMAIL,
                        app_password=config.ZOHO_APP_PASSWORD,
                    )

                    if result["ok"]:
                        sent_ok += 1
                        save_status(seo.url, "📨 Contacted")
                        save_sent_email(emails[0])
                        sent_emails.add(emails[0].lower().strip())
                    else:
                        errors += 1
                        st.warning(f"❌ `{seo.url}` → {result['error']}")

                    prog.progress((i + 1) / len(targets))

                log.empty()
                prog.empty()

                st.session_state["send_summary"] = {
                    "sent": sent_ok, "no_contact": no_contact, "errors": errors
                }
                st.rerun()

    if "send_summary" in st.session_state:
        s = st.session_state["send_summary"]
        st.success(
            f"✅ Отправка завершена  |  Отправлено: **{s['sent']}**  |  "
            f"Нет контакта: **{s['no_contact']}**  |  Ошибок: **{s['errors']}**"
        )
        if st.button("✖ Закрыть", key="close_summary"):
            del st.session_state["send_summary"]
            st.rerun()

    st.divider()
    st.subheader(f"Results ({len(filtered)} leads)")

    for idx, (seo, lead_score, temp) in enumerate(filtered):
        if not seo.reachable:
            continue

        statuses     = load_statuses()
        lead_status  = statuses.get(seo.url, "🟡 New")
        niche_flag   = "" if seo.niche_match else "  ⚠️ Off-niche?"
        header = f"{lead_status}  {temp}  |  **{seo.url}**  |  Score: {lead_score}  |  Issues: {seo.issues_count}{niche_flag}"
        with st.expander(header, expanded=(idx < 3)):

            # Status selector
            status_cols = st.columns(len(STATUS_OPTIONS) + 1)
            status_cols[0].markdown("**Status:**")
            for si, opt in enumerate(STATUS_OPTIONS):
                if status_cols[si + 1].button(opt, key=f"st_{idx}_{si}",
                                               type="primary" if lead_status == opt else "secondary"):
                    save_status(seo.url, opt)
                    st.rerun()

            if not seo.niche_match and niche != "All niches":
                st.warning(f"⚠️ Site may not match **{niche}** niche — verify manually before outreach.", icon="🔍")

            st.divider()
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("**SEO Issues**")
                for iss in seo.issues:
                    st.markdown(f"- {iss}")

                if seo.ai and seo.ai.ai_verdict:
                    st.markdown("**AI Verdict**")
                    st.info(seo.ai.ai_verdict)

                st.markdown("**Technical**")
                tech_info = {
                    "Title":     f"{seo.title[:60]}… ({seo.title_len} ch)" if seo.title else "❌ Missing",
                    "H1":        f"{seo.h1_text[:60]}…" if seo.h1_text else "❌ Missing",
                    "Meta desc": f"{seo.meta_desc[:60]}… ({seo.meta_desc_len} ch)" if seo.meta_desc else "❌ Missing",
                    "Sitemap":   "✅" if seo.has_sitemap else "❌",
                    "Robots":    "✅" if seo.has_robots else "❌",
                    "Schema":    ("✅ " + ", ".join(seo.schema_types)) if seo.schema_types else ("✅" if seo.has_schema else "❌"),
                    "Pages scanned": str(seo.pages_scanned),
                }
                for k, v in tech_info.items():
                    st.markdown(f"**{k}:** {v}")

            with col_b:
                st.markdown("**Contacts**")
                contact_key = f"contacts_{idx}"
                email_key   = f"email_{idx}"

                if contact_key not in st.session_state:
                    if st.button("🔍 Find contacts", key=f"btn_contact_{idx}"):
                        with st.spinner("Searching contact pages…"):
                            contacts = find_contacts(seo.url)
                        st.session_state[contact_key] = contacts

                if contact_key in st.session_state:
                    contacts = st.session_state[contact_key]
                    if contacts["emails"]:
                        st.markdown("📧 **Emails:** " + ", ".join(contacts["emails"]))
                    else:
                        st.markdown("📧 **Emails:** not found")
                    if contacts["phones"]:
                        st.markdown("📞 **Phones:** " + ", ".join(contacts["phones"]))
                    if contacts["owner"]:
                        st.markdown(f"👤 **Owner:** {contacts['owner']}")

                    socials = []
                    if contacts.get("linkedin"):
                        socials.append(f"[LinkedIn]({contacts['linkedin']})")
                    if contacts.get("facebook"):
                        socials.append(f"[Facebook]({contacts['facebook']})")
                    if contacts.get("instagram"):
                        socials.append(f"[Instagram]({contacts['instagram']})")
                    if contacts.get("twitter"):
                        socials.append(f"[Twitter/X]({contacts['twitter']})")
                    if socials:
                        st.markdown("🌐 **Social:** " + " · ".join(socials))
                    elif not contacts["emails"]:
                        st.caption("💡 No contacts found on site — check social media pages manually")

                    st.divider()
                    st.markdown("**Cold Email**")

                    if email_key not in st.session_state:
                        if st.button("✉️ Generate cold email", key=f"btn_email_{idx}"):
                            with st.spinner("Writing personalized email…"):
                                em = generate_email(
                                    url=seo.url,
                                    query=saved_query,
                                    issues=seo.issues,
                                    verdict=seo.ai.ai_verdict if seo.ai else "",
                                    owner=contacts.get("owner", ""),
                                    email=contacts["emails"][0] if contacts["emails"] else "",
                                )
                            st.session_state[email_key] = em

                    if email_key in st.session_state:
                        em = st.session_state[email_key]
                        if em.get("error"):
                            st.error(em["error"])
                        else:
                            st.markdown(f"**Subject:** `{em['subject']}`")
                            st.code(em["body"], language=None)

# ── Scan history ─────────────────────────────────────────────────────────────
history = load_history()
if history:
    st.divider()
    with st.expander(f"📋 Scan history ({len(history)} runs)", expanded=False):
        for h in history:
            hot_tag  = f"💥 {h['hot']}" if h['hot']  else ""
            fire_tag = f"🔥 {h['fire']}" if h['fire'] else ""
            warm_tag = f"🌤 {h['warm']}" if h['warm'] else ""
            tags = "  ".join(t for t in [hot_tag, fire_tag, warm_tag] if t)
            st.markdown(
                f"`{h['date']}`  **{h['query']}**  ·  {h['geo']}  ·  {h['niche']}  "
                f"·  {h['total']} sites  ·  {tags}"
            )

else:
    st.markdown("""
    ### How it works

    1. **Enter a search query** — or click a quick template above
    2. **Click Run** — searches Google, scans up to 100 sites for SEO issues
    3. **Review leads** — ranked by score (higher = worse SEO = hotter lead)
    4. **Find contacts** — email, phone, LinkedIn per site
    5. **Generate cold email** — AI writes personalized outreach
    6. **Export to Excel** — color-coded spreadsheet

    ---
    **Lead temperatures:**
    - 💥 Critical (70+) — severe SEO issues, very hot lead
    - 🔥 Hot (45–70) — significant issues
    - 🌤 Warm (20–45) — some issues worth mentioning
    - ❄️ Cold (0–20) — decent SEO, probably not interested
    """)
