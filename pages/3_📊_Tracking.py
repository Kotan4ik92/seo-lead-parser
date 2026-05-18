"""
Email tracking stats page.
"""

import datetime
import streamlit as st
from modules.app_shared import require_auth, render_sidebar
from modules.database import get_email_tracking_stats, get_today_send_count

st.set_page_config(page_title="Email Tracking — SEO Lead Parser", page_icon="📊", layout="wide")

require_auth()
render_sidebar(show_lead_filters=False, show_email_settings=True)

st.title("📊 Email Tracking")
st.markdown(
    "Track every cold email sent. Click through rates are measurable via Google Analytics "
    "using the **UTM parameters** embedded in each email's seobro.com link."
)

records = get_email_tracking_stats()

if not records:
    st.info("No emails sent yet. Go to the Search page, find leads, and send cold emails.")
    st.stop()

# ── Summary stats ─────────────────────────────────────────────────────────────
today = datetime.date.today().isoformat()
sent_today  = sum(1 for r in records if r["sent_at"].startswith(today))
sent_total  = len(records)
unique_leads = len({r["lead_url"] for r in records})

c1, c2, c3 = st.columns(3)
c1.metric("📨 Sent today",    sent_today)
c2.metric("📬 Total sent",    sent_total)
c3.metric("🌐 Unique leads",  unique_leads)

st.divider()

# ── UTM tip ───────────────────────────────────────────────────────────────────
with st.expander("💡 How to see clicks in Google Analytics", expanded=False):
    st.markdown("""
1. Open **Google Analytics 4** → Reports → Acquisition → Traffic acquisition
2. Filter by **Session source** = `cold_email`
3. Or go to **Explore** → create a Free-form report, dimension = `Campaign` (= `seo_outreach`)
4. Each row = one lead's domain — you can see exactly who clicked

**UTM parameters used in every email:**
- `utm_source=cold_email`
- `utm_medium=email`
- `utm_campaign=seo_outreach`
- `utm_content=<lead-domain>` ← unique per lead
""")

# ── Sent emails table ─────────────────────────────────────────────────────────
st.subheader(f"Sent emails ({sent_total} total)")

search = st.text_input("🔍 Filter by domain or email", placeholder="e.g. example.com")

shown = [
    r for r in records
    if not search or search.lower() in r["lead_url"].lower() or search.lower() in r["to_email"].lower()
]

if not shown:
    st.warning("No records match the filter.")
else:
    for r in shown:
        date_str  = r["sent_at"][:10]
        time_str  = r["sent_at"][11:16]
        utm_link  = (
            f"https://seobro.com?utm_source=cold_email&utm_medium=email"
            f"&utm_campaign=seo_outreach&utm_content={r['utm_content']}"
        )
        st.markdown(
            f"`{date_str} {time_str}` — "
            f"[{r['lead_url']}]({r['lead_url']}) → `{r['to_email']}`  \n"
            f"**Subject:** {r['subject']}  \n"
            f"**UTM:** [{utm_link}]({utm_link})"
        )
        st.divider()
