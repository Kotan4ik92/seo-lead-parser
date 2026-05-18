"""
Telegram notifications for key CRM events.
Sends a message when a lead status changes to a notable stage.
"""

import requests
import config

NOTIFY_ON_STATUSES = {"✅ Interested", "🤝 In Negotiation", "🏆 Won"}


def send_telegram(text: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id":    config.TELEGRAM_CHAT_ID,
                "text":       text,
                "parse_mode": "HTML",
            },
            timeout=8,
        )
        return resp.status_code == 200
    except Exception:
        return False


def notify_status_change(lead_url: str, new_status: str) -> bool:
    """Send a Telegram alert when a lead reaches a notable status."""
    if new_status not in NOTIFY_ON_STATUSES:
        return False

    emoji_map = {
        "✅ Interested":      "🔥",
        "🤝 In Negotiation": "💼",
        "🏆 Won":            "🎉",
    }
    emoji = emoji_map.get(new_status, "📌")

    text = (
        f"{emoji} <b>Lead update</b>\n\n"
        f"<b>Status:</b> {new_status}\n"
        f"<b>URL:</b> <a href='{lead_url}'>{lead_url}</a>"
    )
    return send_telegram(text)
