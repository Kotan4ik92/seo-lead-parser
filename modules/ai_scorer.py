"""
Батч AI-оценка качества SEO по всем просканированным страницам сайта.
Один запрос на весь сайт — экономим токены.
Модель: gpt-4.1-mini
"""

import json
from dataclasses import dataclass

from openai import OpenAI

import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


@dataclass
class AiScore:
    title_score:  int = -1
    title_issue:  str = ""
    h1_score:     int = -1
    h1_issue:     str = ""
    meta_score:   int = -1
    meta_issue:   str = ""
    schema_score: int = -1
    schema_issue: str = ""
    robots_score: int = -1
    robots_issue: str = ""
    ai_total:     int = 0
    ai_verdict:   str = ""
    error:        str = ""


PROMPT = """\
You are an SEO auditor. Evaluate SEO quality across {n} scanned pages of this site.

Site: {base_url}
Niche/Query: {query}

Scanned pages:
{pages_block}

Robots.txt snippet: {robots}

Score each category 0-10 (0=missing/terrible, 10=excellent).
Look for PATTERNS across pages: e.g. if most titles are generic → low score.

Return ONLY valid JSON, no markdown:
{{
  "title_score": 0-10,
  "title_issue": "main issue with titles or empty string",
  "h1_score": 0-10,
  "h1_issue": "...",
  "meta_score": 0-10,
  "meta_issue": "...",
  "schema_score": 0-10,
  "schema_issue": "...",
  "robots_score": 0-10,
  "robots_issue": "...",
  "verdict": "2-sentence overall SEO verdict"
}}

Scoring guide: 0-3 poor, 4-6 mediocre, 7-9 decent, 10 excellent."""


def evaluate_site(base_url: str, query: str,
                  pages: list[dict], robots_snippet: str = "") -> AiScore:
    """
    pages: list of {url, title, h1, meta, has_schema}
    Один запрос на весь сайт.
    """
    if not config.OPENAI_API_KEY:
        return AiScore(error="OPENAI_API_KEY не задан")

    pages_block = ""
    for i, p in enumerate(pages, 1):
        pages_block += (
            f"[{i}] {p.get('url', '')}\n"
            f"  Title: {p.get('title') or '(missing)'}\n"
            f"  H1:    {p.get('h1') or '(missing)'}\n"
            f"  Meta:  {p.get('meta') or '(missing)'}\n"
            f"  Schema: {'Yes' if p.get('has_schema') else 'No'}\n\n"
        )

    result = AiScore()
    try:
        resp = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": PROMPT.format(
                n=len(pages),
                base_url=base_url,
                query=query,
                pages_block=pages_block,
                robots=robots_snippet[:300] if robots_snippet else "(missing)",
            )}],
            temperature=0,
            max_tokens=500,
        )

        data = json.loads(resp.choices[0].message.content.strip())
        result.title_score  = int(data.get("title_score", 5))
        result.title_issue  = data.get("title_issue", "")
        result.h1_score     = int(data.get("h1_score", 5))
        result.h1_issue     = data.get("h1_issue", "")
        result.meta_score   = int(data.get("meta_score", 5))
        result.meta_issue   = data.get("meta_issue", "")
        result.schema_score = int(data.get("schema_score", 5))
        result.schema_issue = data.get("schema_issue", "")
        result.robots_score = int(data.get("robots_score", 5))
        result.robots_issue = data.get("robots_issue", "")
        result.ai_verdict   = data.get("verdict", "")
        result.ai_total = sum(
            max(0, 10 - s) for s in [
                result.title_score, result.h1_score, result.meta_score,
                result.schema_score, result.robots_score,
            ]
        )
    except Exception as e:
        result.error = str(e)

    return result
