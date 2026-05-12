"""
Отправка холодных писем через Zoho Mail SMTP.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ZOHO_SMTP = "smtppro.zoho.eu"
ZOHO_PORT = 465


def send_cold_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    app_password: str,
    from_name: str = "Alex | SEOBRO",
) -> dict:
    """
    Returns {"ok": True} or {"ok": False, "error": str}
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{from_email}>"
        msg["To"]      = to_email
        msg["Reply-To"] = from_email

        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP_SSL(ZOHO_SMTP, ZOHO_PORT) as server:
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
