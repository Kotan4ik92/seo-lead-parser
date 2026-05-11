"""
Выбор репрезентативных страниц из sitemap.xml.
Логика: читаем sitemap → категоризируем URL → берём до 15 страниц.
"""

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

# Паттерны по типу страниц и лимиты выборки
PAGE_TYPES = [
    ("category",  r"/categor|/collection|/cat/|/department|/genre|/section",  3),
    ("product",   r"/product|/item/|/p/|/shop/|/listing|/sku",               4),
    ("blog",      r"/blog|/news|/article|/post|/press",                       2),
    ("info",      r"/about|/contact|/faq|/return|/privacy|/terms|/service|/pricing", 5),
]


def parse_sitemap(xml_text: str) -> list[str]:
    try:
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]+"', "", xml_text)
        root = ET.fromstring(clean)
        return [loc.text.strip() for loc in root.findall(".//url/loc") if loc.text]
    except Exception:
        return []


def select_pages(base_url: str, all_urls: list[str], max_pages: int = 15) -> list[str]:
    """Возвращает список URL для сканирования (главная + до max_pages страниц)."""
    if not all_urls:
        return [base_url]

    base_netloc = urlparse(base_url).netloc.replace("www.", "")

    # Фильтр: только тот же домен
    same = [
        u for u in all_urls
        if urlparse(u).netloc.replace("www.", "") == base_netloc
    ]
    if not same:
        return [base_url]

    selected = [base_url]
    counts = {t: 0 for t, _, _ in PAGE_TYPES}
    others: list[str] = []

    for url in same:
        path = urlparse(url).path.lower()
        if url.rstrip("/") == base_url.rstrip("/"):
            continue

        matched = False
        for ptype, pattern, limit in PAGE_TYPES:
            if re.search(pattern, path) and counts[ptype] < limit:
                selected.append(url)
                counts[ptype] += 1
                matched = True
                break

        if not matched:
            others.append(url)

    # Добираем прочими если не набрали нужное кол-во
    for url in others:
        if len(selected) >= max_pages:
            break
        selected.append(url)

    return selected[:max_pages]
