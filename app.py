"""
SEO Lead Parser — main page (Search & Results).
Запуск локально : streamlit run app.py
Деплой         : Streamlit Community Cloud (github.com → connect repo)
"""

import json
import time
import random
import datetime
import requests

import streamlit as st

import config
from modules.app_shared import (
    require_auth, render_sidebar,
    GSHEET_SA, GSHEET_ID,
    STATUS_OPTIONS, FALLBACK_TEMPLATES,
)
from modules.database import (
    get_all_statuses, save_status,
    get_all_lead_data, mark_contacted, save_note, get_followup_due,
    append_history, get_sent_emails, save_sent_email,
    get_today_send_count, increment_send_count,
    record_email_sent,
)
from modules.notifier       import notify_status_change
from modules.serp_scraper   import scrape_serp
from modules.seo_scanner    import scan
from modules.scorer         import score
from modules.contact_finder import find_contacts
from modules.email_writer   import generate_email
from modules.sheets_writer  import write_to_excel
from modules.gsheets_writer import push_to_gsheets
from modules.email_sender   import send_cold_email

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEO Lead Parser",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_auth()
settings = render_sidebar()

niche        = settings["niche"]
geo          = settings["geo"]
geo_label    = settings["geo_label"]
lang_label   = settings["lang_label"]
lang_restrict = settings["lang_restrict"]
max_results  = settings["max_results"]
max_pages    = settings["max_pages"]
score_min    = settings["score_min"]
score_max    = settings["score_max"]
min_issues   = settings["min_issues"]
daily_limit  = settings["daily_limit"]


# ── AI template generator ─────────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_ai_templates(openai_key: str, niche: str, geo: str, lang: str) -> list[str]:
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


def _notify_status_change(url: str, status: str):
    notify_status_change(url, status)


# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🔍 SEO Lead Parser")
st.markdown("Find websites with poor SEO → turn them into warm leads.")

# ── Follow-up reminders ───────────────────────────────────────────────────────
followup_due = get_followup_due(days=7)
if followup_due:
    _all_lead_data = get_all_lead_data()
    with st.expander(f"⏰ Follow-up needed — {len(followup_due)} leads waiting 7+ days", expanded=True):
        st.caption("These leads have been in **📨 Contacted** status for 7+ days — time to send a follow-up.")
        for fu_url, fu_days in sorted(followup_due, key=lambda x: -x[1]):
            note = _all_lead_data.get(fu_url, {}).get("note", "")
            note_str = f" · 📝 *{note}*" if note else ""
            st.markdown(f"- [{fu_url}]({fu_url}) — **{fu_days} days** since last contact{note_str}")

# ── AI query templates ────────────────────────────────────────────────────────
tmpl_label_col, tmpl_refresh_col = st.columns([5, 1])
tmpl_label_col.caption("Quick templates (AI picks trending niches for today):")
if tmpl_refresh_col.button("🔄", help="Regenerate templates", use_container_width=True):
    get_ai_templates.clear()

with st.spinner("Loading templates…"):
    TEMPLATES = get_ai_templates(config.OPENAI_API_KEY, niche, geo_label, lang_label)

tmpl_cols = st.columns(6)
for i, tmpl in enumerate(TEMPLATES):
    if tmpl_cols[i].button(tmpl, key=f"tmpl_{i}", use_container_width=True):
        st.session_state["query_input"] = tmpl

# ── Query input ───────────────────────────────────────────────────────────────
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
    for key in ["scan_results", "scan_query", "scan_excel"]:
        st.session_state.pop(key, None)

    config.SEARCH_GEO         = geo
    config.MAX_RESULTS        = max_results
    config.MAX_PAGES_PER_SITE = max_pages

    niche_tag = f" | Niche: {niche}" if niche != "All niches" else ""
    lang_tag  = f" | Lang: {lang_label}" if lang_restrict else ""
    st.info(f"Searching: **{query}** | Geo: {geo_label}{niche_tag}{lang_tag} | Up to {max_results} sites")

    with st.spinner("🌐 Fetching search results…"):
        urls = scrape_serp(query, max_results=max_results, lang_restrict=lang_restrict, niche=niche)

    if not urls:
        st.error("No URLs found. Check your Serper.dev API key or try a different query.")
        st.stop()

    st.success(f"Found **{len(urls)}** sites. Scanning SEO now…")

    progress_bar = st.progress(0)
    status_text  = st.empty()

    session = requests.Session()
    session.headers.update({
        "User-Agent":    random.choice(config.USER_AGENTS),
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

    st.session_state["scan_results"] = all_results
    st.session_state["scan_query"]   = query

    _hot  = sum(1 for _, s, _ in all_results if s >= 70)
    _fire = sum(1 for _, s, _ in all_results if 45 <= s < 70)
    _warm = sum(1 for _, s, _ in all_results if 20 <= s < 45)
    append_history(query, geo_label, niche, len(all_results), _hot, _fire, _warm)

    safe_q   = query.replace(" ", "_").replace("/", "-")[:40]
    st.session_state["scan_excel_filename"] = f"leads_{safe_q}.xlsx"

elif run_btn and not query:
    st.warning("Please enter a search query.")

# ── Results ───────────────────────────────────────────────────────────────────
if "scan_results" in st.session_state:
    all_results = st.session_state["scan_results"]
    saved_query = st.session_state.get("scan_query", "")

    filtered = [
        (seo, s, t) for seo, s, t in all_results
        if score_min <= s <= score_max and seo.issues_count >= min_issues
    ]

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

    # ── Export ────────────────────────────────────────────────────────────────
    export_col1, export_col2 = st.columns([2, 3])

    if "scan_excel_filename" in st.session_state:
        filename = st.session_state["scan_excel_filename"]
        write_to_excel(
            st.session_state["scan_results"],
            st.session_state.get("scan_query", ""),
            filename=filename,
            contacts=st.session_state.get("contacts_emails", {}),
            statuses=get_all_statuses(),
        )
        with open(filename, "rb") as f:
            excel_bytes = f.read()
        export_col1.download_button(
            "📥 Download Excel",
            data=excel_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if GSHEET_SA and GSHEET_ID:
        if export_col2.button("📊 Push to Google Sheets", use_container_width=True):
            with st.spinner("Pushing to Google Sheets…"):
                try:
                    sheet_url = push_to_gsheets(
                        results=st.session_state["scan_results"],
                        query=st.session_state.get("scan_query", "scan"),
                        sa_info=GSHEET_SA,
                        spreadsheet_id=GSHEET_ID,
                        contacts=st.session_state.get("contacts_emails", {}),
                        statuses=get_all_statuses(),
                    )
                    st.success(f"✅ Done! [Open Google Sheets]({sheet_url})", icon="📊")
                except Exception as e:
                    st.error(f"Google Sheets error: {e}")

    # ── Auto-send emails ──────────────────────────────────────────────────────
    if config.ZOHO_EMAIL and config.ZOHO_APP_PASSWORD:
        st.divider()
        st.markdown("**📤 Auto-send cold emails**")

        today_sent = get_today_send_count()
        remaining  = max(0, daily_limit - today_sent)

        if remaining == 0:
            st.warning(f"⛔ Daily limit reached ({daily_limit} emails). Resets tomorrow.")
        else:
            st.caption(f"📬 Sent today: **{today_sent} / {daily_limit}** — {remaining} remaining")

        st.caption("**Skip leads with these flags:**")
        excl_cols = st.columns(4)
        excl_agency      = excl_cols[0].checkbox("🔄 Has SEO agency?", value=False)
        excl_large       = excl_cols[1].checkbox("📦 Large site",      value=False)
        excl_marketplace = excl_cols[2].checkbox("🏪 Marketplace?",    value=True)
        excl_offniche    = excl_cols[3].checkbox("⚠️ Off-niche?",      value=False)

        statuses_preview = get_all_statuses()
        preview_targets  = [
            (seo, sc, t) for seo, sc, t in all_results
            if seo.reachable and sc >= 20
            and statuses_preview.get(seo.url, "🟡 New") == "🟡 New"
            and not (excl_agency      and seo.has_seo_agency)
            and not (excl_large       and seo.large_site)
            and not (excl_marketplace and seo.is_marketplace)
            and not (excl_offniche    and not seo.niche_match)
        ]
        st.caption(
            f"Will send to **{min(len(preview_targets), remaining)}** leads "
            f"({len(preview_targets)} match filters, {remaining} quota remaining)"
        )

        if remaining > 0 and st.button("📤 Send emails", type="primary"):
            statuses    = get_all_statuses()
            sent_emails = get_sent_emails()
            targets = [
                (seo, sc, t) for seo, sc, t in all_results
                if seo.reachable and sc >= 20
                and statuses.get(seo.url, "🟡 New") == "🟡 New"
                and not (excl_agency      and seo.has_seo_agency)
                and not (excl_large       and seo.large_site)
                and not (excl_marketplace and seo.is_marketplace)
                and not (excl_offniche    and not seo.niche_match)
            ][:remaining]

            if not targets:
                st.info("No leads match current filters.")
            else:
                st.info(f"Sending to **{len(targets)}** leads. Starting…")
                prog = st.progress(0)
                log  = st.empty()
                sent_ok, no_contact, errors = 0, 0, 0

                for i, (seo, sc, temp) in enumerate(targets):
                    log.markdown(f"**[{i+1}/{len(targets)}]** `{seo.url}` — finding contacts…")
                    contacts = find_contacts(seo.url)
                    emails   = contacts.get("emails", [])

                    if not emails or emails[0].lower().strip() in sent_emails:
                        no_contact += 1
                        prog.progress((i + 1) / len(targets))
                        continue

                    log.markdown(f"**[{i+1}/{len(targets)}]** `{seo.url}` — writing email…")
                    em = generate_email(
                        url=seo.url, query=saved_query, issues=seo.issues,
                        verdict=seo.ai.ai_verdict if seo.ai else "",
                        owner=contacts.get("owner", ""), email=emails[0], niche=niche,
                    )

                    if em.get("error") or not em.get("body"):
                        errors += 1
                        st.warning(f"❌ `{seo.url}` → email gen error: {em.get('error', 'empty body')}")
                        prog.progress((i + 1) / len(targets))
                        continue

                    log.markdown(f"**[{i+1}/{len(targets)}]** `{seo.url}` — sending to {emails[0]}…")
                    result = send_cold_email(
                        to_email=emails[0], subject=em["subject"], body=em["body"],
                        from_email=config.ZOHO_EMAIL, app_password=config.ZOHO_APP_PASSWORD,
                        lead_url=seo.url,
                    )

                    if result["ok"]:
                        sent_ok += 1
                        save_status(seo.url, "📨 Contacted")
                        save_sent_email(emails[0])
                        mark_contacted(seo.url)
                        increment_send_count()
                        record_email_sent(seo.url, emails[0], em["subject"], result.get("utm_content", ""))
                        sent_emails.add(emails[0].lower().strip())
                        if "contacts_emails" not in st.session_state:
                            st.session_state["contacts_emails"] = {}
                        st.session_state["contacts_emails"][seo.url] = emails[0]
                        if i < len(targets) - 1:
                            time.sleep(random.uniform(40, 60))
                    else:
                        errors += 1
                        st.warning(f"❌ `{seo.url}` → {result['error']}")

                    prog.progress((i + 1) / len(targets))

                log.empty()
                prog.empty()
                st.session_state["send_summary"] = {
                    "sent": sent_ok, "no_contact": no_contact, "errors": errors,
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

    # ── Bulk actions ──────────────────────────────────────────────────────────
    reachable_urls = [seo.url for seo, _, _ in filtered if seo.reachable]
    if reachable_urls:
        with st.expander("☑️ Bulk actions", expanded=False):
            bulk_cols = st.columns([3, 1, 1, 1, 1])
            bulk_cols[0].caption("Change status for **all visible** leads at once:")
            for bi, opt in enumerate(STATUS_OPTIONS):
                if bulk_cols[bi + 1].button(opt, key=f"bulk_{bi}", use_container_width=True):
                    for url in reachable_urls:
                        save_status(url, opt)
                    st.success(f"Updated {len(reachable_urls)} leads → {opt}")
                    st.rerun()

    _lead_data_cache = get_all_lead_data()
    _statuses_cache  = get_all_statuses()

    for idx, (seo, lead_score, temp) in enumerate(filtered):
        if not seo.reachable:
            with st.expander(f"⛔ Недоступен  |  **{seo.url}**", expanded=False):
                col_r1, col_r2 = st.columns([3, 1])
                col_r1.caption("Сайт не ответил во время сканирования.")
                if col_r2.button("🔄 Повторить", key=f"retry_{idx}"):
                    with st.spinner(f"Повторное сканирование {seo.url}…"):
                        retry_session = requests.Session()
                        retry_session.headers.update({
                            "User-Agent": random.choice(config.USER_AGENTS),
                            "Accept-Language": "en-US,en;q=0.9",
                        })
                        new_seo = scan(seo.url, retry_session, query=saved_query, niche=niche)
                        new_score, new_temp = score(new_seo)
                    all_results[all_results.index((seo, lead_score, temp))] = (new_seo, new_score, new_temp)
                    st.session_state["scan_results"] = all_results
                    st.rerun()
            continue

        lead_status   = _statuses_cache.get(seo.url, "🟡 New")
        lead_entry    = _lead_data_cache.get(seo.url, {})
        contact_count = lead_entry.get("contact_count", 0)
        contact_badge = f"  📨 ×{contact_count}" if contact_count > 0 else ""

        flags = []
        if not seo.niche_match:    flags.append("⚠️ Off-niche?")
        if seo.has_seo_agency:     flags.append("🔄 Has SEO agency?")
        if seo.large_site:         flags.append("📦 Large site")
        if seo.is_marketplace:     flags.append("🏪 Marketplace?")
        flags_str = "  " + "  ".join(flags) if flags else ""
        header = (
            f"{lead_status}  {temp}  |  **{seo.url}**  |  "
            f"Score: {lead_score}  |  Issues: {seo.issues_count}{contact_badge}{flags_str}"
        )

        with st.expander(header, expanded=(idx < 3)):
            st.markdown("**Status:**")
            row1, row2 = STATUS_OPTIONS[:4], STATUS_OPTIONS[4:]
            r1_cols = st.columns(len(row1))
            for si, opt in enumerate(row1):
                if r1_cols[si].button(opt, key=f"st_{idx}_{si}",
                                      type="primary" if lead_status == opt else "secondary",
                                      use_container_width=True):
                    save_status(seo.url, opt)
                    _notify_status_change(seo.url, opt)
                    st.rerun()
            r2_cols = st.columns(len(row2))
            for si, opt in enumerate(row2):
                if r2_cols[si].button(opt, key=f"st_{idx}_{si + 4}",
                                      type="primary" if lead_status == opt else "secondary",
                                      use_container_width=True):
                    save_status(seo.url, opt)
                    _notify_status_change(seo.url, opt)
                    st.rerun()

            if not seo.niche_match and niche != "All niches":
                st.warning(f"⚠️ Site may not match **{niche}** niche — verify manually before outreach.", icon="🔍")
            if seo.has_seo_agency:
                st.info("🔄 Likely already working with an SEO agency — but worth reaching out anyway.", icon="💡")
            if seo.large_site:
                st.warning("📦 Large site (300+ pages in sitemap) — may be outside ideal client size.", icon="📦")
            if seo.is_marketplace:
                st.warning("🏪 Marketplace signals detected — verify if this is a good fit.", icon="🏪")

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
                    if contacts.get("linkedin"):  socials.append(f"[LinkedIn]({contacts['linkedin']})")
                    if contacts.get("facebook"):  socials.append(f"[Facebook]({contacts['facebook']})")
                    if contacts.get("instagram"): socials.append(f"[Instagram]({contacts['instagram']})")
                    if contacts.get("twitter"):   socials.append(f"[Twitter/X]({contacts['twitter']})")
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
                                    url=seo.url, query=saved_query, issues=seo.issues,
                                    verdict=seo.ai.ai_verdict if seo.ai else "",
                                    owner=contacts.get("owner", ""),
                                    email=contacts["emails"][0] if contacts["emails"] else "",
                                    niche=niche,
                                )
                            st.session_state[email_key] = em

                    if email_key in st.session_state:
                        em = st.session_state[email_key]
                        if em.get("error"):
                            st.error(em["error"])
                        else:
                            st.markdown(f"**Subject:** `{em['subject']}`")
                            st.code(em["body"], language=None)

            # ── Notes ─────────────────────────────────────────────────────────
            st.divider()
            st.markdown("**📝 Notes**")
            note_key   = f"note_{idx}"
            saved_note = lead_entry.get("note", "")
            if note_key not in st.session_state:
                st.session_state[note_key] = saved_note
            note_val = st.text_area(
                "Notes", value=st.session_state[note_key],
                key=f"note_area_{idx}",
                label_visibility="collapsed",
                placeholder="Add notes about this lead…",
                height=80,
            )
            if st.button("💾 Save note", key=f"save_note_{idx}"):
                save_note(seo.url, note_val)
                st.session_state[note_key] = note_val
                st.success("Saved", icon="✅")

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
