"""
Shared constants, secrets loading, and sidebar renderer for all pages.
"""

import json
import datetime
import streamlit as st
import config
from modules.database import get_today_send_count, get_api_usage_this_month, migrate_from_json

# ── One-time setup ────────────────────────────────────────────────────────────
migrate_from_json()

# ── Streamlit Cloud secrets ───────────────────────────────────────────────────
GSHEET_SA:    dict | None = None
GSHEET_ID:    str  = ""
APP_PASSWORD: str  = ""

try:
    if "SERPER_API_KEY" in st.secrets:
        config.SERPER_API_KEY = st.secrets["SERPER_API_KEY"]
    if "OPENAI_API_KEY" in st.secrets:
        config.OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    if "gcp_service_account" in st.secrets:
        GSHEET_SA = dict(st.secrets["gcp_service_account"])
    if "GSHEET_ID" in st.secrets:
        GSHEET_ID = st.secrets["GSHEET_ID"]
    if "ZOHO_EMAIL" in st.secrets:
        config.ZOHO_EMAIL = st.secrets["ZOHO_EMAIL"]
    if "ZOHO_APP_PASSWORD" in st.secrets:
        config.ZOHO_APP_PASSWORD = st.secrets["ZOHO_APP_PASSWORD"]
    if "APP_PASSWORD" in st.secrets:
        APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

STATUS_OPTIONS = ["🟡 New", "📨 Contacted", "✅ Interested", "❌ Skip"]

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

NICHE_OPTIONS = [
    "All niches", "Ecommerce", "HoReCa", "SaaS",
    "Local Services", "Real Estate", "Healthcare",
    "Beauty & Wellness", "Travel & Tourism", "Fitness & Sport",
    "Education", "Legal & Finance",
]

NICHE_ICONS = {
    "All niches":        "🌐",
    "Ecommerce":         "🛒",
    "HoReCa":           "🍽️",
    "SaaS":             "💻",
    "Local Services":   "🔧",
    "Real Estate":      "🏠",
    "Healthcare":       "🏥",
    "Beauty & Wellness": "💅",
    "Travel & Tourism": "✈️",
    "Fitness & Sport":  "🏋️",
    "Education":        "🎓",
    "Legal & Finance":  "⚖️",
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


# ── Auth gate ─────────────────────────────────────────────────────────────────

def require_auth():
    """Stops page rendering if password gate is enabled and user is not logged in."""
    if not APP_PASSWORD:
        return
    if st.session_state.get("authenticated"):
        return
    st.markdown("<div style='max-width:360px; margin:80px auto 0'>", unsafe_allow_html=True)
    st.title("🔍 SEO Lead Parser")
    st.caption("SEOBRO internal tool — team access only")
    pwd = st.text_input("Password", type="password", placeholder="Enter password…")
    if st.button("Sign in", type="primary", use_container_width=True):
        if pwd == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(show_lead_filters: bool = True, show_email_settings: bool = True) -> dict:
    """
    Renders the sidebar and returns a dict with selected settings.
    Keys: niche, geo, geo_label, lang_label, lang_restrict,
          max_results, max_pages, score_min, score_max, min_issues, daily_limit
    """
    with st.sidebar:
        st.title("⚙️ Settings")

        serper_ok = "✅" if config.SERPER_API_KEY else "❌ not set"
        openai_ok = "✅" if config.OPENAI_API_KEY else "❌ not set"
        gsheet_ok = "✅" if (GSHEET_SA and GSHEET_ID) else "❌ not set"
        zoho_ok   = "✅" if (config.ZOHO_EMAIL and config.ZOHO_APP_PASSWORD) else "❌ not set"

        serper_used  = get_api_usage_this_month("serper")
        serper_limit = 2500
        serper_pct   = serper_used / serper_limit
        serper_color = "🟢" if serper_pct < 0.7 else ("🟡" if serper_pct < 0.9 else "🔴")
        st.caption(f"Serper.dev: {serper_ok}  {serper_color} {serper_used}/{serper_limit} в месяц")
        st.caption(f"OpenAI API: {openai_ok}")
        st.caption(f"Google Sheets: {gsheet_ok}")
        st.caption(f"Zoho Mail: {zoho_ok}")
        if not config.SERPER_API_KEY or not config.OPENAI_API_KEY:
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
                st.markdown("<div style='font-size:26px; line-height:1'>🌐</div>", unsafe_allow_html=True)

        max_results = st.slider("Max sites to scan", 5, 100, 30, step=5)
        max_pages   = st.slider("Pages per site (sitemap)", 5, 20, 15, step=5)

        score_min, score_max, min_issues, daily_limit = 0, 100, 0, 25

        if show_lead_filters:
            st.divider()
            st.caption("**Lead filters**")
            score_min, score_max = st.slider(
                "Score range", min_value=0, max_value=100, value=(0, 100), step=5,
            )
            min_issues = st.slider("Min technical issues", 0, 10, 0, step=1,
                                   help="Show only sites with at least N technical problems")

        if show_email_settings:
            st.divider()
            st.caption("**Email sending**")
            daily_limit = st.slider("Daily send limit", 5, 50, 25, step=5,
                                    help="Max emails per day to protect seobro.com reputation")
            today_count = get_today_send_count()
            st.caption(f"Sent today: **{today_count} / {daily_limit}**")

        st.divider()
        st.markdown("Made with ❤️ for SEO agencies")

    return {
        "niche":        niche,
        "geo":          geo,
        "geo_label":    geo_label,
        "lang_label":   lang_label,
        "lang_restrict": lang_restrict,
        "max_results":  max_results,
        "max_pages":    max_pages,
        "score_min":    score_min,
        "score_max":    score_max,
        "min_issues":   min_issues,
        "daily_limit":  daily_limit,
    }
