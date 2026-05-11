"""
AI-генератор персонализированных холодных писем на основе SEO-проблем сайта.
Один запрос на сайт — GPT-4.1-mini.
"""

import json
from openai import OpenAI

import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


PROMPT = """\
You are writing a cold outreach email on behalf of SEOBRO (seobro.com) — a boutique SEO agency specializing in SaaS, Ecommerce, Hotels, and Real Estate. The agency focuses on real results: qualified pipeline, not vanity metrics.

Write a short, personalized email to the owner of this website offering SEO services.

Website: {url}
Business niche: {query}
Owner name (if known): {owner}
Contact email: {email}

SEO issues found on their site:
{issues_block}

AI SEO verdict: {verdict}

Rules:
- Write in English
- Maximum 120 words total (subject line + body)
- Be specific — mention 2-3 REAL issues from their site, not generic phrases
- Sign off as SEOBRO team (no individual name needed)
- Friendly and confident tone — not pushy, not salesy
- No fake statistics ("97% of businesses...")
- CTA: offer a free SEO audit with results delivered by email — do NOT suggest calls, meetings, or phone conversations
- Mention SEOBRO by name naturally once in the body

Return ONLY valid JSON, no markdown:
{{
  "subject": "email subject line",
  "body": "email body text with \\n for line breaks"
}}"""


def generate_email(
    url: str,
    query: str,
    issues: list[str],
    verdict: str = "",
    owner: str = "",
    email: str = "",
) -> dict:
    """
    Returns {"subject": str, "body": str, "error": str}
    """
    if not config.OPENAI_API_KEY:
        return {"subject": "", "body": "", "error": "OPENAI_API_KEY не задан"}

    # Build issues block — skip technical noise, keep meaningful ones
    meaningful = [i for i in issues if i not in ("Крупный бренд — не целевой лид", "Сайт недоступен")]
    if not meaningful and not verdict:
        return {"subject": "", "body": "", "error": "Нет данных для письма"}

    issues_block = "\n".join(f"- {i}" for i in meaningful[:8]) if meaningful else "(see verdict below)"

    try:
        resp = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": PROMPT.format(
                url=url,
                query=query,
                owner=owner or "Business Owner",
                email=email or "(unknown)",
                issues_block=issues_block,
                verdict=verdict or "(not available)",
            )}],
            temperature=0.7,
            max_tokens=400,
        )

        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if model added them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        return {
            "subject": data.get("subject", ""),
            "body":    data.get("body", ""),
            "error":   "",
        }

    except Exception as e:
        return {"subject": "", "body": "", "error": str(e)}
