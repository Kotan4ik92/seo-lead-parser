"""
SEO-сканирование сайта:
  1. Полная проверка главной страницы (технические сигналы)
  2. Sitemap → выбор до 15 страниц
  3. Лёгкое сканирование каждой (title/h1/meta/schema)
  4. Один батч-запрос в AI на весь сайт
"""

import re
import json
import time
import random
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config
from modules.ai_scorer import AiScore, evaluate_site
from modules.page_selector import parse_sitemap, select_pages


@dataclass
class SeoResult:
    url: str = ""
    reachable: bool = False

    # Технические (по главной)
    https: bool = False
    has_sitemap: bool = False
    has_robots: bool = False
    robots_snippet: str = ""
    canonical_ok: bool = False
    lang_set: bool = False
    viewport_set: bool = False
    ps_mobile: int = -1
    ps_desktop: int = -1

    # Данные главной страницы
    title: str = ""
    title_len: int = 0
    meta_desc: str = ""
    meta_desc_len: int = 0
    h1_count: int = 0
    h1_text: str = ""
    has_schema: bool = False
    schema_types: list[str] = field(default_factory=list)
    robots_has_sitemap: bool = False

    # Мультистраничные данные
    pages_scanned: int = 0
    pages_data: list = field(default_factory=list)  # [{url, title, h1, meta, has_schema}]

    # AI-оценка (по всем страницам)
    ai: AiScore = field(default_factory=AiScore)

    # Итог
    issues: list[str] = field(default_factory=list)
    issues_count: int = 0
    niche_match: bool = True       # False = сайт скорее всего не в нише
    has_seo_agency: bool = False   # True = вероятно уже работает с SEO-агентством
    large_site: bool = False       # True = большой сайт (300+ страниц)
    is_marketplace: bool = False   # True = признаки маркетплейса


def _fetch(url: str, session: requests.Session, timeout: int = None, retries: int = 2):
    timeout = timeout or config.REQUEST_TIMEOUT
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                session.headers.update({"User-Agent": random.choice(config.USER_AGENTS)})
                time.sleep(attempt * 2 + random.uniform(0.5, 1.5))
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code < 500:
                return resp
        except Exception:
            if attempt == retries:
                return None
    return None


def _extract_page_data(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    h1_tags = soup.find_all("h1")
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    has_schema = bool(
        soup.find("script", type="application/ld+json") or
        soup.find(attrs={"itemscope": True})
    )
    return {
        "url":        url,
        "title":      title_tag.get_text(strip=True)[:120] if title_tag else "",
        "h1":         h1_tags[0].get_text(strip=True)[:120] if h1_tags else "",
        "meta":       meta.get("content", "").strip()[:200] if meta else "",
        "has_schema": has_schema,
    }


def scan(url: str, session: requests.Session, query: str = "", niche: str = "") -> SeoResult:
    result = SeoResult(url=url)
    issues = []

    # --- Главная страница ---
    resp = _fetch(url, session)
    if resp is None or resp.status_code >= 400:
        result.reachable = False
        result.issues = ["Сайт недоступен"]
        result.issues_count = 1
        return result

    result.reachable = True
    soup = BeautifulSoup(resp.text, "html.parser")
    final_url = resp.url

    result.https = final_url.startswith("https://")

    # Title
    title_tag = soup.find("title")
    result.title = title_tag.get_text(strip=True) if title_tag else ""
    result.title_len = len(result.title)
    if not result.title:
        issues.append("Нет тега Title")
    elif result.title_len < 30:
        issues.append(f"Title слишком короткий ({result.title_len} симв.)")
    elif result.title_len > 70:
        issues.append(f"Title слишком длинный ({result.title_len} симв.)")

    # Meta Description
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    result.meta_desc = meta.get("content", "").strip() if meta else ""
    result.meta_desc_len = len(result.meta_desc)
    if not result.meta_desc:
        issues.append("Нет Meta Description")
    elif result.meta_desc_len < 80:
        issues.append(f"Meta Description слишком короткий ({result.meta_desc_len} симв.)")
    elif result.meta_desc_len > 165:
        issues.append(f"Meta Description слишком длинный ({result.meta_desc_len} симв.)")

    # H1
    h1_tags = soup.find_all("h1")
    result.h1_count = len(h1_tags)
    result.h1_text = h1_tags[0].get_text(strip=True)[:100] if h1_tags else ""
    if result.h1_count == 0:
        issues.append("Нет тега H1")
    elif result.h1_count > 1:
        issues.append(f"Несколько H1 ({result.h1_count} шт.)")

    # Schema markup — detect types
    schema_types = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                t = data.get("@type")
                if t:
                    schema_types.append(t if isinstance(t, str) else t[0])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        t = item.get("@type")
                        if t:
                            schema_types.append(t if isinstance(t, str) else t[0])
        except Exception:
            pass
    for tag in soup.find_all(attrs={"itemscope": True}):
        t = tag.get("itemtype", "")
        if t:
            schema_types.append(t.split("/")[-1])
    result.has_schema   = bool(schema_types) or bool(soup.find(attrs={"itemscope": True}))
    result.schema_types = list(dict.fromkeys(schema_types))[:5]
    if not result.has_schema:
        issues.append("Нет Schema markup")

    canonical = soup.find("link", rel="canonical")
    result.canonical_ok = bool(canonical and canonical.get("href"))

    html_tag = soup.find("html")
    result.lang_set = bool(html_tag and html_tag.get("lang"))
    if not result.lang_set:
        issues.append("Не задан атрибут lang")

    viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    result.viewport_set = bool(viewport)
    if not result.viewport_set:
        issues.append("Нет meta viewport")

    # Robots.txt
    robots_resp = _fetch(urljoin(url, "/robots.txt"), session, timeout=6)
    if robots_resp and robots_resp.status_code == 200 and len(robots_resp.text) > 10:
        result.has_robots = True
        result.robots_snippet = robots_resp.text[:300]
        result.robots_has_sitemap = "sitemap" in robots_resp.text.lower()
        if not result.robots_has_sitemap:
            issues.append("robots.txt не содержит ссылку на Sitemap")
    else:
        issues.append("Нет robots.txt")

    # Sitemap + выбор страниц
    sitemap_resp = _fetch(urljoin(url, "/sitemap.xml"), session, timeout=6)
    sitemap_urls: list[str] = []
    if sitemap_resp and sitemap_resp.status_code == 200:
        result.has_sitemap = True
        sitemap_urls = parse_sitemap(sitemap_resp.text)
    else:
        issues.append("Нет sitemap.xml")

    # Крупный бренд — sitemap >500 страниц → не наш клиент, пропускаем
    if len(sitemap_urls) > 500:
        result.issues = ["Крупный бренд — не целевой лид"]
        result.issues_count = 1
        result.reachable = False
        return result

    pages_to_scan = select_pages(final_url, sitemap_urls, max_pages=config.MAX_PAGES_PER_SITE)

    # --- Сканируем выбранные страницы ---
    pages_data = []
    # Главная уже загружена
    pages_data.append(_extract_page_data(final_url, resp.text))

    for page_url in pages_to_scan:
        if page_url.rstrip("/") == final_url.rstrip("/"):
            continue
        if len(pages_data) >= config.MAX_PAGES_PER_SITE:
            break
        page_resp = _fetch(page_url, session, timeout=10)
        if page_resp and page_resp.status_code == 200:
            pages_data.append(_extract_page_data(page_url, page_resp.text))
        time.sleep(0.8 + random.uniform(0.1, 0.3))

    result.pages_data = pages_data
    result.pages_scanned = len(pages_data)

    # --- AI батч-оценка по всем страницам ---
    if config.OPENAI_API_KEY:
        result.ai = evaluate_site(
            base_url=final_url,
            query=query,
            pages=pages_data,
            robots_snippet=result.robots_snippet,
        )

    result.issues       = issues
    result.issues_count = len(issues)

    # Niche heuristic check
    if niche and niche != "All niches":
        result.niche_match = _check_niche(
            niche,
            f"{result.title} {result.h1_text} {result.meta_desc}".lower()
        )

    # ── ICP flags ──────────────────────────────────────────────────────────────
    page_text = resp.text.lower()

    # Large site flag (300–500 pages — not auto-disqualified but worth noting)
    result.large_site = 300 <= len(sitemap_urls) <= 500

    # Marketplace flag
    marketplace_signals = ["marketplace", "list your business", "become a seller",
                           "sell on ", "vendor portal", "list your store"]
    result.is_marketplace = any(s in page_text for s in marketplace_signals)

    # SEO agency flag — check footer/bottom of page for agency credits
    seo_agency_signals = [
        "seo by ", "seo services by", "digital marketing by",
        "powered by seo", "marketing agency", "seo agency",
        "designed & seo", "website by ", "web design & seo",
        "search engine optimization by",
    ]
    footer_area = page_text[-8000:]  # check last ~8kb (footer area)
    result.has_seo_agency = any(s in footer_area for s in seo_agency_signals)

    return result


NICHE_KEYWORDS = {
    "Ecommerce":        ["shop", "store", "buy", "cart", "product", "order", "price", "ecommerce", "checkout"],
    "HoReCa":          ["restaurant", "hotel", "cafe", "bar", "menu", "dining", "catering", "food", "drink", "book a table"],
    "SaaS":            ["software", "platform", "app", "dashboard", "trial", "pricing", "saas", "subscription", "api"],
    "Local Services":  ["service", "contractor", "repair", "plumber", "electrician", "cleaning", "local", "call us"],
    "Real Estate":     ["property", "real estate", "apartment", "house", "rent", "sale", "listing", "realty", "agent"],
    "Healthcare":      ["clinic", "medical", "doctor", "health", "patient", "hospital", "therapy", "dental", "pharmacy"],
    "Beauty & Wellness": ["salon", "spa", "beauty", "wellness", "skincare", "massage", "nail", "hair"],
    "Travel & Tourism": ["travel", "tour", "vacation", "hotel", "flight", "booking", "resort", "destination"],
    "Fitness & Sport": ["gym", "fitness", "workout", "sport", "training", "coach", "yoga", "crossfit"],
    "Education":       ["school", "academy", "course", "learn", "education", "training", "university", "degree", "study"],
    "Legal & Finance": ["law", "attorney", "legal", "finance", "accounting", "tax", "insurance", "investment", "advisor"],
}


def _check_niche(niche: str, text: str) -> bool:
    keywords = NICHE_KEYWORDS.get(niche, [])
    return any(kw in text for kw in keywords)
