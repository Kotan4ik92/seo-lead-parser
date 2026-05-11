"""
Извлечение контактов с сайта: email, телефон, имя владельца, LinkedIn.
Проверяем /contact, /about, /team и главную страницу.
"""

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config

CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team", "/"]

EMAIL_RE    = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE    = re.compile(r"(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
LINKEDIN_RE = re.compile(r"https?://(www\.)?linkedin\.com/(?:company|in)/[^\s\"'>]+")

SKIP_EMAILS = {"example@", "email@", "your@", "info@example", "test@", "noreply@",
               "no-reply@", "support@example", "admin@example"}


def _clean_email(email: str) -> str:
    return email.lower().strip()


def _is_valid_email(email: str) -> bool:
    if any(skip in email for skip in SKIP_EMAILS):
        return False
    domain = email.split("@")[-1]
    return "." in domain and len(domain) > 3


def _fetch(url: str, session: requests.Session) -> str | None:
    try:
        resp = session.get(url, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def _extract_from_html(html: str, base_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    emails = list({
        _clean_email(e) for e in EMAIL_RE.findall(text)
        if _is_valid_email(e)
    })

    phones = list({
        "".join(filter(str.isdigit, p[1])) for p in PHONE_RE.findall(text)
        if len("".join(filter(str.isdigit, p[1]))) >= 10
    })

    linkedin_urls = list({
        m.group(0) for m in (LINKEDIN_RE.search(str(tag))
                              for tag in soup.find_all(href=True))
        if m
    })

    # Пробуем найти имя владельца — ищем паттерны "Founded by", "Owner:", "CEO:"
    owner = ""
    for pattern in [r"(?:founded by|owner|ceo|president|director)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
                    r"([A-Z][a-z]+ [A-Z][a-z]+),?\s+(?:owner|ceo|founder|president)"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            owner = match.group(1).strip()
            break

    return {
        "emails":   emails[:5],
        "phones":   [p[:10] for p in phones[:3]],
        "linkedin": linkedin_urls[0] if linkedin_urls else "",
        "owner":    owner,
    }


def find_contacts(base_url: str) -> dict:
    """Возвращает словарь с контактами сайта."""
    result = {"emails": [], "phones": [], "linkedin": "", "owner": ""}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    })

    all_emails, all_phones = set(), set()
    linkedin, owner = "", ""

    for path in CONTACT_PATHS:
        html = _fetch(urljoin(base_url, path), session)
        if not html:
            continue
        data = _extract_from_html(html, base_url)
        all_emails.update(data["emails"])
        all_phones.update(data["phones"])
        if not linkedin and data["linkedin"]:
            linkedin = data["linkedin"]
        if not owner and data["owner"]:
            owner = data["owner"]

    # Фильтруем email по домену сайта (приоритет)
    site_domain = urlparse(base_url).netloc.replace("www.", "")
    site_emails = [e for e in all_emails if site_domain in e]
    other_emails = [e for e in all_emails if site_domain not in e]

    result["emails"]   = (site_emails + other_emails)[:3]
    result["phones"]   = list(all_phones)[:2]
    result["linkedin"] = linkedin
    result["owner"]    = owner

    return result
