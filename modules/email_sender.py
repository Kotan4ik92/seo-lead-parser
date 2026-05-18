"""
Отправка холодных писем через Zoho Mail SMTP.
Письма отправляются в двух частях: plain text + HTML с UTM-ссылками.
"""

import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlencode, urlparse, quote_plus

ZOHO_SMTP = "smtppro.zoho.eu"
ZOHO_PORT = 465

UTM_BASE_PARAMS = {
    "utm_source":   "cold_email",
    "utm_medium":   "email",
    "utm_campaign": "seo_outreach",
}


def build_utm_url(base_url: str, utm_content: str) -> str:
    params = {**UTM_BASE_PARAMS, "utm_content": utm_content}
    return f"{base_url.rstrip('/')}?{urlencode(params)}"


def _plain_to_html(plain: str, utm_content: str) -> str:
    """Convert plain-text email body to minimal HTML with UTM links."""
    # Escape HTML special chars
    html = (
        plain
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    # Make seobro.com a tracked clickable link
    tracked_url = build_utm_url("https://seobro.com", utm_content)
    html = re.sub(
        r"(?<![\"'])(?<!\w)seobro\.com(?!/\S)",
        f'<a href="{tracked_url}">seobro.com</a>',
        html,
        flags=re.IGNORECASE,
    )

    # Convert line breaks
    html = html.replace("\n", "<br>\n")

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;font-size:14px;color:#222;line-height:1.6;max-width:600px">
{html}
</body>
</html>"""


def _utm_content_from_url(lead_url: str) -> str:
    """Extract clean domain from lead URL for use as utm_content."""
    try:
        parsed = urlparse(lead_url if "://" in lead_url else f"https://{lead_url}")
        domain = parsed.netloc or parsed.path
        return quote_plus(domain.replace("www.", ""))
    except Exception:
        return quote_plus(lead_url[:50])


def send_cold_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    app_password: str,
    from_name: str = "Alex | SEOBRO",
    lead_url: str = "",
) -> dict:
    """
    Returns {"ok": True, "utm_content": str} or {"ok": False, "error": str}
    """
    try:
        utm_content = _utm_content_from_url(lead_url) if lead_url else "unknown"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{from_email}>"
        msg["To"]      = to_email
        msg["Reply-To"] = from_email

        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(_plain_to_html(body, utm_content), "html", "utf-8"))

        with smtplib.SMTP_SSL(ZOHO_SMTP, ZOHO_PORT) as server:
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())

        return {"ok": True, "utm_content": utm_content}
    except Exception as e:
        return {"ok": False, "error": str(e), "utm_content": ""}
