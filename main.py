"""
SEO Lead Parser — точка входа.
Запуск: python main.py
"""

import sys
import time
import random
import requests

import config
from modules.serp_scraper import scrape_serp
from modules.seo_scanner  import scan
from modules.scorer        import score
from modules.sheets_writer import write_to_excel, write_to_csv


def main():
    query = config.SEARCH_QUERY
    print("=" * 60)
    print(f"  SEO Lead Parser")
    print(f"  Запрос : {query}")
    print(f"  Лимит  : {config.MAX_RESULTS} сайтов")
    print("=" * 60)

    # 1. Собираем URL из SERP
    urls = scrape_serp(query, max_results=config.MAX_RESULTS)
    if not urls:
        print("\n[!] Не удалось получить URL из Google. Возможные причины:")
        print("    • Google заблокировал запросы — попробуйте позже или через VPN")
        print("    • Проверьте интернет-соединение")
        sys.exit(1)

    print(f"\n[OK] Найдено {len(urls)} сайтов. Начинаем сканирование…\n")

    # 2. Сканируем каждый сайт
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(config.USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    })

    all_results = []
    for i, url in enumerate(urls, 1):
        print(f"[{i:>3}/{len(urls)}] Сканирую {url} …", end=" ", flush=True)
        seo   = scan(url, session, query=query)
        lead_score, temp = score(seo)
        all_results.append((seo, lead_score, temp))
        print(f"{temp}  ({lead_score} баллов, {seo.issues_count} проблем)")

        time.sleep(config.REQUEST_DELAY + random.uniform(0, 0.8))

    # 3. Сортируем: горячие лиды — наверху
    all_results.sort(key=lambda x: x[1], reverse=True)

    # 4. Вывод в Google Sheets или CSV
    print("\n[INFO] Сохраняем результаты…")
    safe_query = query.replace(" ", "_").replace("/", "-")[:40]
    timestamp  = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M")
    filename   = f"leads_{safe_query}_{timestamp}.xlsx"
    write_to_excel(all_results, query, filename=filename)

    # 5. Итоговая статистика
    hot   = sum(1 for _, s, _ in all_results if s >= 45)
    warm  = sum(1 for _, s, _ in all_results if 20 <= s < 45)
    cold  = sum(1 for _, s, _ in all_results if s < 20)
    dead  = sum(1 for r, _, _ in all_results if not r.reachable)

    print("\n" + "=" * 60)
    print("  ИТОГИ")
    print(f"  Всего просканировано : {len(all_results)}")
    print(f"  💥🔥 Горячих лидов   : {hot}")
    print(f"  🌤  Тёплых           : {warm}")
    print(f"  ❄️  Холодных         : {cold}")
    print(f"  ⛔  Недоступных      : {dead}")
    print("=" * 60)


if __name__ == "__main__":
    main()
