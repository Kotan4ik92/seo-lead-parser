"""
Scan history page.
"""

import streamlit as st
from modules.app_shared import require_auth, render_sidebar
from modules.database import get_history

st.set_page_config(page_title="Scan History — SEO Lead Parser", page_icon="📋", layout="wide")

require_auth()
render_sidebar(show_lead_filters=False, show_email_settings=False)

st.title("📋 Scan History")

history = get_history()

if not history:
    st.info("No scan runs yet. Go to the Search page and run your first scan.")
    st.stop()

st.caption(f"Last **{len(history)}** scan runs — newest first.")
st.divider()

for h in history:
    hot_tag  = f"💥 {h['hot']}"  if h["hot"]  else ""
    fire_tag = f"🔥 {h['fire']}" if h["fire"] else ""
    warm_tag = f"🌤 {h['warm']}" if h["warm"] else ""
    tags = "  ".join(t for t in [hot_tag, fire_tag, warm_tag] if t) or "❄️ all cold"
    st.markdown(
        f"`{h['date']}`  **{h['query']}**  ·  {h['geo']}  ·  {h['niche']}  "
        f"·  {h['total']} sites  ·  {tags}"
    )
