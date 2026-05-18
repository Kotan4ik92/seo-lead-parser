"""
Email tracking + outreach analytics page.
"""

import datetime
import streamlit as st
from modules.app_shared import require_auth, render_sidebar, STATUS_OPTIONS
from modules.database import (
    get_email_tracking_stats, get_today_send_count,
    get_all_statuses, get_history,
)

st.set_page_config(page_title="Analytics — SEO Lead Parser", page_icon="📊", layout="wide")

require_auth()
render_sidebar(show_lead_filters=False, show_email_settings=True)

st.title("📊 Outreach Analytics")

# ── Funnel summary ────────────────────────────────────────────────────────────
st.subheader("📈 Conversion funnel")

statuses = get_all_statuses()
counts   = {opt: 0 for opt in STATUS_OPTIONS}
for s in statuses.values():
    if s in counts:
        counts[s] += 1

total_leads  = len(statuses)
contacted    = counts.get("📨 Contacted", 0)
interested   = counts.get("✅ Interested", 0)
negotiation  = counts.get("🤝 In Negotiation", 0)
won          = counts.get("🏆 Won", 0)
lost         = counts.get("💀 Lost", 0)
skipped      = counts.get("❌ Skip", 0)

if total_leads == 0:
    st.info("No leads yet. Run a search on the main page.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🟡 New",            counts.get("🟡 New", 0))
c2.metric("📨 Contacted",      contacted)
c3.metric("✅ Interested",     interested)
c4.metric("🤝 Negotiation",   negotiation)
c5.metric("🏆 Won",            won)

active   = contacted + interested + negotiation + won
response_rate = f"{interested / max(contacted, 1) * 100:.0f}%"
win_rate      = f"{won / max(active, 1) * 100:.1f}%"
contact_rate  = f"{active / max(total_leads - skipped, 1) * 100:.0f}%"

m1, m2, m3 = st.columns(3)
m1.metric("Contact rate",  contact_rate, help="% of leads that were contacted")
m2.metric("Response rate", response_rate, help="Interested / Contacted")
m3.metric("Win rate",      win_rate,      help="Won / all active leads")

st.divider()

# ── Scan history by niche & geo ───────────────────────────────────────────────
history = get_history()
if history:
    st.subheader("🌍 Scans by niche")

    niche_stats: dict[str, dict] = {}
    for h in history:
        niche = h.get("niche", "Unknown")
        if niche not in niche_stats:
            niche_stats[niche] = {"scans": 0, "total": 0, "hot": 0, "fire": 0}
        niche_stats[niche]["scans"] += 1
        niche_stats[niche]["total"] += h.get("total", 0)
        niche_stats[niche]["hot"]   += h.get("hot", 0)
        niche_stats[niche]["fire"]  += h.get("fire", 0)

    niche_rows = sorted(niche_stats.items(), key=lambda x: x[1]["total"], reverse=True)
    hdr = st.columns([3, 1, 1, 1, 1])
    hdr[0].caption("**Niche**")
    hdr[1].caption("**Scans**")
    hdr[2].caption("**Sites**")
    hdr[3].caption("**💥 Critical**")
    hdr[4].caption("**🔥 Hot**")
    for niche, s in niche_rows:
        row = st.columns([3, 1, 1, 1, 1])
        row[0].write(niche)
        row[1].write(s["scans"])
        row[2].write(s["total"])
        row[3].write(s["hot"])
        row[4].write(s["fire"])

    st.divider()

# ── Email tracking table ──────────────────────────────────────────────────────
records = get_email_tracking_stats()
st.subheader(f"📨 Sent emails ({len(records)} total)")

if not records:
    st.info("No emails sent yet. Go to the Search page, find leads, and send cold emails.")
else:
    today = datetime.date.today().isoformat()
    sent_today = sum(1 for r in records if r["sent_at"].startswith(today))
    unique_leads = len({r["lead_url"] for r in records})

    ec1, ec2, ec3 = st.columns(3)
    ec1.metric("📨 Sent today",   sent_today)
    ec2.metric("📬 Total sent",   len(records))
    ec3.metric("🌐 Unique leads", unique_leads)

    with st.expander("💡 How to track clicks in Google Analytics", expanded=False):
        st.markdown("""
1. **Google Analytics 4** → Reports → Acquisition → Traffic acquisition
2. Filter by **Session source** = `cold_email`
3. Or go to **Explore** → Free-form, dimension = `Campaign` (= `seo_outreach`)
4. `utm_content` = lead domain — see exactly who clicked

**UTM params in every email:** `utm_source=cold_email` · `utm_medium=email` · `utm_campaign=seo_outreach` · `utm_content=<lead-domain>`
""")

    search = st.text_input("🔍 Filter by domain or email", placeholder="e.g. example.com")
    shown  = [
        r for r in records
        if not search
        or search.lower() in r["lead_url"].lower()
        or search.lower() in r["to_email"].lower()
    ]

    for r in shown[:100]:
        date_str = r["sent_at"][:10]
        time_str = r["sent_at"][11:16]
        utm_link = (
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
