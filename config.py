import os

# ═══════════════════════════════════════════════════════
#  Меняйте SEARCH_QUERY + SEARCH_GEO перед каждым запуском
#  (или задайте прямо в UI приложения)
# ═══════════════════════════════════════════════════════
#
#  🛒 ECOMMERCE (us/gb/ca/au):
#    "online furniture store USA"        "buy supplements online USA"
#    "pet supplies store online UK"      "skincare ecommerce store USA"
#
#  🍽 HORECA (us/gb/ca/au):
#    "boutique hotel New York"           "restaurant chain Chicago"
#    "catering company London"           "cafe franchise Canada"
#
#  💻 SAAS (us/gb/ca):
#    "project management software SMB"   "CRM software small business"
#    "HR software startup"               "accounting software SMB USA"
#
SEARCH_QUERY = "online furniture store USA"
MAX_RESULTS   = 50
SEARCH_LANG   = "en"
SEARCH_GEO    = "us"   # us / gb / ca / au / de / fr

# --- API Keys ---
# Leave empty here — enter them in the app sidebar,
# or set via Streamlit Cloud secrets (Settings → Secrets):
#   SERPER_API_KEY = "your_key"
#   OPENAI_API_KEY = "your_key"
SERPER_API_KEY   = os.environ.get("SERPER_API_KEY", "")
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL     = "gpt-4.1-mini"
ZOHO_EMAIL       = os.environ.get("ZOHO_EMAIL", "")
ZOHO_APP_PASSWORD = os.environ.get("ZOHO_APP_PASSWORD", "")

# --- Сканирование ---
REQUEST_TIMEOUT      = 15
REQUEST_DELAY        = 2.5
MAX_PAGES_PER_SITE   = 15
PAGESPEED_API_KEY    = os.getenv("PAGESPEED_KEY", "")

# --- Google Sheets (не используется в Streamlit-версии) ---
GOOGLE_SHEET_ID   = ""
WORKSHEET_NAME    = "Лиды"
CREDENTIALS_FILE  = "credentials.json"

# --- User Agents ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]
