"""
Парсинг выдачи через Serper.dev API.
Бесплатно: 2500 запросов при регистрации (без карты).
"""

import time
import random
from urllib.parse import urlparse

import requests

import config
from modules.database import record_api_call

SERPER_URL = "https://google.serper.dev/search"

SKIP_DOMAINS = {
    # Поисковики и соцсети
    "google.com", "bing.com", "yahoo.com", "duckduckgo.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "reddit.com", "pinterest.com", "tiktok.com",
    "youtube.com", "vimeo.com",
    # Энциклопедии / медиа
    "wikipedia.org", "wikihow.com", "wikimedia.org",
    "forbes.com", "nytimes.com", "wsj.com", "bloomberg.com",
    "businessinsider.com", "inc.com", "entrepreneur.com",
    "cnn.com", "foxnews.com", "foxbusiness.com", "nbcnews.com",
    "usatoday.com", "washingtonpost.com", "theguardian.com",
    "huffpost.com", "buzzfeed.com", "vox.com", "curbed.com",
    "brownstoner.com", "apartments.com", "zillow.com", "realtor.com",
    # Директории и агрегаторы
    "yelp.com", "bbb.org", "angi.com", "thumbtack.com",
    "angieslist.com", "homeadvisor.com", "houzz.com",
    "bark.com", "checkatrade.com", "trustpilot.com",
    "tripadvisor.com", "yellowpages.com", "superpages.com",
    "manta.com", "expertise.com", "ontoplist.com", "networx.com",
    "homeguide.com", "modernize.com", "nearbyhunt.com",
    "local.yahoo.com", "local.com", "citysearch.com",
    "mapquest.com", "yp.com", "merchantcircle.com",
    "findaplumbernewyork.com", "hirerush.com", "procore.com",
    # Работа и фриланс
    "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "craigslist.org", "airtasker.com", "taskrabbit.com",
    "upwork.com", "fiverr.com", "thumbtack.com",
    # Маркетплейсы
    "amazon.com", "ebay.com", "etsy.com", "walmart.com",
    # Государственные
    "gov", "nyc.gov", "usa.gov",
    # Прочее
    "glassdoor.com", "sitejabber.com", "porch.com",
    "ensun.io", "clutch.co", "goodfirms.co",
}


def _base(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.netloc else ""


def _is_skip(domain: str) -> bool:
    """Match exact domain OR any parent domain (catches subdomains like en.wikipedia.org)."""
    if domain in SKIP_DOMAINS:
        return True
    parts = domain.split(".")
    for i in range(1, len(parts)):
        if ".".join(parts[i:]) in SKIP_DOMAINS:
            return True
    return False


NICHE_BOOSTERS = {
    "Ecommerce":        "online store OR shop OR buy OR ecommerce",
    "HoReCa":          "restaurant OR hotel OR cafe OR catering",
    "SaaS":            "software OR platform OR app OR saas",
    "Local Services":  "local service OR company OR contractor",
    "Real Estate":     "real estate OR property OR realty",
    "Healthcare":      "clinic OR medical OR health OR doctor",
    "Beauty & Wellness": "salon OR spa OR beauty OR wellness",
    "Travel & Tourism": "travel OR tour OR vacation OR resort",
    "Fitness & Sport": "gym OR fitness OR sport OR training",
    "Education":       "school OR academy OR course OR training",
    "Legal & Finance": "law firm OR attorney OR accountant OR finance",
}


def scrape_serp(query: str, max_results: int = 100,
                lang_restrict: str = "", niche: str = "") -> list[str]:
    boosted = query
    if niche and niche != "All niches" and niche in NICHE_BOOSTERS:
        boosted = f"{query} {NICHE_BOOSTERS[niche]}"
    urls = _scrape(boosted, max_results, lang_restrict)
    if not urls and lang_restrict:
        print(f"[SERP] No results with lang filter, retrying without it…")
        urls = _scrape(boosted, max_results, "")
    return urls


def _scrape(query: str, max_results: int, lang_restrict: str) -> list[str]:
    if not config.SERPER_API_KEY:
        print("[SERP] ОШИБКА: не задан SERPER_API_KEY в config.py")
        return []

    all_urls: list[str] = []
    page = 1

    print(f"[SERP] Serper.dev поиск: «{query}» — нужно {max_results} сайтов")

    while len(all_urls) < max_results:
        payload = {
            "q":    query,
            "gl":   config.SEARCH_GEO,
            "hl":   config.SEARCH_LANG,
            "num":  10,
            "page": page,
        }
        if lang_restrict:
            payload["lr"] = lang_restrict
        headers = {
            "X-API-KEY":    config.SERPER_API_KEY,
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(SERPER_URL, json=payload, headers=headers, timeout=15)
            record_api_call("serper")
        except requests.RequestException as e:
            print(f"[SERP] Ошибка сети: {e}")
            break

        if resp.status_code == 429:
            print("[SERP] Лимит запросов исчерпан.")
            break

        if resp.status_code != 200:
            print(f"[SERP] HTTP {resp.status_code}: {resp.text[:200]}")
            break

        items = resp.json().get("organic", [])
        if not items:
            print("[SERP] Больше результатов нет")
            break

        new_count = 0
        for item in items:
            base = _base(item.get("link", ""))
            domain = urlparse(base).netloc.replace("www.", "")
            # Check domain AND all parent domains (catches en.wikipedia.org etc.)
            if domain and not _is_skip(domain) and base not in all_urls:
                all_urls.append(base)
                new_count += 1

        print(f"[SERP] Страница {page}: +{new_count} сайтов (итого {len(all_urls)})")
        page += 1
        time.sleep(0.3 + random.uniform(0.1, 0.2))

    return all_urls[:max_results]
