"""
SEO Lead Parser — Streamlit Web App
Запуск локально : streamlit run app.py
Деплой         : Streamlit Community Cloud (github.com → connect repo)
"""

import io
import time
import random
import requests

import streamlit as st

import config

# On Streamlit Cloud, secrets are injected via st.secrets
# Locally, keys come from config.py or the sidebar
try:
    import streamlit as _st_pre
    if "SERPER_API_KEY" in _st_pre.secrets:
        config.SERPER_API_KEY = _st_pre.secrets["SERPER_API_KEY"]
    if "OPENAI_API_KEY" in _st_pre.secrets:
        config.OPENAI_API_KEY = _st_pre.secrets["OPENAI_API_KEY"]
except Exception:
    pass

from modules.serp_scraper  import scrape_serp
from modules.seo_scanner   import scan
from modules.scorer        import score
from modules.contact_finder import find_contacts
from modules.email_writer  import generate_email
from modules.sheets_writer import write_to_excel

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEO Lead Parser",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar — settings ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    serper_key = st.text_input(
        "Serper.dev API Key",
        value=config.SERPER_API_KEY,
        type="password",
        help="Get free key at serper.dev (2500 free searches)",
    )
    openai_key = st.text_input(
        "OpenAI API Key",
        value=config.OPENAI_API_KEY,
        type="password",
        help="Used for AI SEO scoring and cold email generation",
    )

    st.divider()
    st.caption("**Search settings**")
    geo = st.selectbox("Market / Geo", ["us", "gb", "ca", "au", "de", "fr"], index=0)
    max_results = st.slider("Max sites to scan", 5, 100, 30, step=5)
    max_pages = st.slider("Pages per site (sitemap)", 5, 20, 15, step=5)

    st.divider()
    st.caption("**Lead filter**")
    min_score = st.slider("Minimum lead score", 0, 100, 0)

    st.divider()
    st.markdown("Made with ❤️ for SEO agencies")

# ── Main area ─────────────────────────────────────────────────────────────────
st.title("🔍 SEO Lead Parser")
st.markdown("Find websites with poor SEO → turn them into warm leads.")

TEMPLATES = [
    "online furniture store USA",
    "restaurant chain Chicago",
    "CRM software small business",
    "pet supplies store online UK",
    "boutique hotel New York",
    "accounting software SMB USA",
]

# Quick query templates (set session state before rendering text_input)
st.caption("Quick templates:")
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
    # Patch config with sidebar values
    config.SERPER_API_KEY  = serper_key
    config.OPENAI_API_KEY  = openai_key
    config.SEARCH_GEO      = geo
    config.MAX_RESULTS     = max_results
    config.MAX_PAGES_PER_SITE = max_pages

    st.info(f"Searching Google for: **{query}** | Geo: {geo} | Up to {max_results} sites")

    # Step 1: SERP
    with st.spinner("🌐 Fetching search results…"):
        urls = scrape_serp(query, max_results=max_results)

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
        seo = scan(url, session, query=query)
        lead_score, temp = score(seo)
        all_results.append((seo, lead_score, temp))
        progress_bar.progress((i + 1) / len(urls))
        time.sleep(config.REQUEST_DELAY + random.uniform(0, 0.5))

    status_text.empty()
    progress_bar.empty()

    # Sort by score descending
    all_results.sort(key=lambda x: x[1], reverse=True)

    # Filter by min score
    filtered = [(seo, s, t) for seo, s, t in all_results if s >= min_score]

    # Step 3: Stats
    hot   = sum(1 for _, s, _ in filtered if s >= 70)
    fire  = sum(1 for _, s, _ in filtered if 45 <= s < 70)
    warm  = sum(1 for _, s, _ in filtered if 20 <= s < 45)
    cold  = sum(1 for _, s, _ in filtered if s < 20)
    dead  = sum(1 for r, _, _ in filtered if not r.reachable)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💥 Critical", hot)
    c2.metric("🔥 Hot",      fire)
    c3.metric("🌤 Warm",     warm)
    c4.metric("❄️ Cold",    cold)
    c5.metric("⛔ Dead",     dead)

    st.divider()

    # Step 4: Save to Excel and offer download
    safe_q = query.replace(" ", "_").replace("/", "-")[:40]
    filename = f"leads_{safe_q}.xlsx"
    write_to_excel(filtered, query, filename=filename)
    with open(filename, "rb") as f:
        excel_bytes = f.read()

    st.download_button(
        "📥 Download Excel",
        data=excel_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()

    # Step 5: Results table with expanders
    st.subheader(f"Results ({len(filtered)} leads)")

    for idx, (seo, lead_score, temp) in enumerate(filtered):
        if not seo.reachable:
            continue

        color = "#d32f2f" if lead_score >= 70 else \
                "#f57c00" if lead_score >= 45 else \
                "#1976d2" if lead_score >= 20 else "#555"

        header = f"{temp}  |  **{seo.url}**  |  Score: {lead_score}"
        with st.expander(header, expanded=(idx < 3)):

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
                    "Title":     f"{seo.title[:60]}…" if seo.title else "❌ Missing",
                    "H1":        f"{seo.h1_text[:60]}…" if seo.h1_text else "❌ Missing",
                    "Meta desc": f"{seo.meta_desc[:60]}…" if seo.meta_desc else "❌ Missing",
                    "Sitemap":   "✅" if seo.has_sitemap else "❌",
                    "Robots":    "✅" if seo.has_robots else "❌",
                    "Schema":    "✅" if seo.has_schema else "❌",
                    "HTTPS":     "✅" if seo.https else "❌",
                    "Pages scanned": str(seo.pages_scanned),
                }
                for k, v in tech_info.items():
                    st.markdown(f"**{k}:** {v}")

            with col_b:
                st.markdown("**Contacts**")
                contact_key = f"contacts_{idx}"
                email_key   = f"email_{idx}"

                # Find contacts on demand
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

                    if contacts["linkedin"]:
                        st.markdown(f"🔗 **LinkedIn:** [{contacts['linkedin']}]({contacts['linkedin']})")

                    if contacts["owner"]:
                        st.markdown(f"👤 **Owner:** {contacts['owner']}")

                    st.divider()
                    st.markdown("**Cold Email**")

                    if email_key not in st.session_state:
                        if st.button("✉️ Generate cold email", key=f"btn_email_{idx}"):
                            with st.spinner("Writing personalized email…"):
                                em = generate_email(
                                    url=seo.url,
                                    query=query,
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
                            st.markdown(f"**Subject:** {em['subject']}")
                            st.text_area(
                                "Body",
                                value=em["body"],
                                height=200,
                                key=f"email_body_{idx}",
                            )

elif run_btn and not query:
    st.warning("Please enter a search query.")

else:
    # Landing state
    st.markdown("""
    ### How it works

    1. **Enter a search query** — e.g. `"online furniture store USA"`
    2. **Click Run** — the app searches Google and scans up to 50 websites
    3. **Review leads** — ranked by SEO problem score (higher = worse SEO = hotter lead)
    4. **Find contacts** — email, phone, LinkedIn for each site
    5. **Generate cold email** — AI writes a personalized outreach email
    6. **Export to Excel** — download color-coded spreadsheet

    ---
    **Lead temperatures:**
    - 💥 Critical (70+) — site has severe SEO issues, very hot lead
    - 🔥 Hot (45-70) — significant issues
    - 🌤 Warm (20-45) — some issues worth mentioning
    - ❄️ Cold (0-20) — decent SEO, probably not interested
    """)
