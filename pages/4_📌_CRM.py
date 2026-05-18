"""
CRM pipeline page — all leads grouped by status with funnel analytics.
"""

import streamlit as st
from modules.app_shared import require_auth, render_sidebar, STATUS_OPTIONS
from modules.database import get_all_statuses, get_all_lead_data, save_status, get_history
from modules.notifier import notify_status_change

st.set_page_config(page_title="CRM Pipeline — SEO Lead Parser", page_icon="📌", layout="wide")

require_auth()
render_sidebar(show_lead_filters=False, show_email_settings=False)

st.title("📌 CRM Pipeline")
st.caption("All leads ever tracked, grouped by status. Move them through the funnel here.")

statuses   = get_all_statuses()
lead_data  = get_all_lead_data()

if not statuses:
    st.info("No leads yet. Run a search on the main page to find leads.")
    st.stop()

# ── Funnel analytics ──────────────────────────────────────────────────────────
st.subheader("📊 Funnel overview")

counts = {opt: 0 for opt in STATUS_OPTIONS}
for url, status in statuses.items():
    if status in counts:
        counts[status] += 1
    else:
        counts["🟡 New"] += 1

cols = st.columns(len(STATUS_OPTIONS))
for i, opt in enumerate(STATUS_OPTIONS):
    cols[i].metric(opt, counts[opt])

total = len(statuses)
interested = counts.get("✅ Interested", 0) + counts.get("🤝 In Negotiation", 0) + counts.get("🏆 Won", 0)
contacted  = counts.get("📨 Contacted", 0)
won        = counts.get("🏆 Won", 0)

if total > 0:
    st.caption(
        f"**{total}** total leads · "
        f"Response rate: **{interested / max(contacted + interested, 1) * 100:.0f}%** · "
        f"Win rate: **{won / max(total, 1) * 100:.1f}%**"
    )

st.divider()

# ── Leads grouped by status ───────────────────────────────────────────────────
# Show only non-empty, non-New statuses first (active pipeline), then New, then Skip
pipeline_order = [
    "✅ Interested", "🤝 In Negotiation", "🏆 Won",
    "📨 Contacted", "🟡 New", "💀 Lost", "❌ Skip",
]

for stage in pipeline_order:
    stage_leads = [(url, data) for url, data in lead_data.items()
                   if statuses.get(url) == stage]
    # Also include leads with this status that have no lead_data entry
    stage_leads_urls_with_data = {url for url, _ in stage_leads}
    for url, s in statuses.items():
        if s == stage and url not in stage_leads_urls_with_data:
            stage_leads.append((url, {}))

    if not stage_leads:
        continue

    with st.expander(f"{stage}  —  {len(stage_leads)} leads", expanded=(stage in {"✅ Interested", "🤝 In Negotiation"})):
        for url, entry in sorted(stage_leads, key=lambda x: x[1].get("contacted_at", ""), reverse=True):
            note          = entry.get("note", "")
            contact_count = entry.get("contact_count", 0)
            contacted_at  = entry.get("contacted_at", "")

            meta_parts = []
            if contacted_at:
                meta_parts.append(f"last contact: {contacted_at}")
            if contact_count:
                meta_parts.append(f"contacted {contact_count}×")
            if note:
                meta_parts.append(f"📝 {note}")
            meta = "  ·  ".join(meta_parts)

            col_url, col_move = st.columns([5, 3])
            col_url.markdown(f"[{url}]({url})" + (f"  \n<small>{meta}</small>" if meta else ""),
                             unsafe_allow_html=True)

            # Move to next / previous status
            curr_idx  = STATUS_OPTIONS.index(stage) if stage in STATUS_OPTIONS else 0
            move_opts = [opt for opt in STATUS_OPTIONS if opt != stage]
            chosen = col_move.selectbox(
                "Move to", move_opts,
                key=f"crm_move_{url}",
                label_visibility="collapsed",
            )
            if col_move.button("Move", key=f"crm_btn_{url}", use_container_width=True):
                save_status(url, chosen)
                notify_status_change(url, chosen)
                st.rerun()

            st.divider()
