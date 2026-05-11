"""
Подсчёт «температуры» лида.
Комбинирует технические проверки + AI-оценку качества.
"""

from modules.seo_scanner import SeoResult

# Вес технических проблем (без HTTPS, canonical снижен)
TECH_WEIGHTS: dict[str, int] = {
    "Нет тега Title":        8,
    "Нет Meta Description":  8,
    "Нет тега H1":           8,
    "Несколько H1":          4,
    "Не задан атрибут lang": 3,
    "Нет meta viewport":     5,
    "Нет sitemap.xml":       6,
    "Нет robots.txt":        4,
    "PageSpeed mobile":      8,
    "PageSpeed desktop":     5,
    "canonical":             2,  # низкий вес по совету
}

TEMPERATURE = {
    (0,  20):  "❄️ Холодный",
    (20, 45):  "🌤 Тёплый",
    (45, 70):  "🔥 Горячий",
    (70, 101): "💥 Критический",
}


def score(result: SeoResult) -> tuple[int, str]:
    if not result.reachable:
        return 0, "⛔ Недоступен"

    # Технические штрафы
    tech = 0
    for issue in result.issues:
        if issue.startswith("[AI]"):
            continue
        for keyword, weight in TECH_WEIGHTS.items():
            if keyword in issue:
                tech += weight
                break

    # AI-штрафы (max 50 → масштабируем до 50 баллов итогового скора)
    ai_penalty = 0
    if result.ai and result.ai.ai_total > 0:
        ai_penalty = result.ai.ai_total  # уже 0-50

    total = min(tech + ai_penalty, 100)

    for (lo, hi), label in TEMPERATURE.items():
        if lo <= total < hi:
            return total, label

    return total, "—"
