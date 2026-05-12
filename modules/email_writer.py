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
You are writing a cold outreach email on behalf of SEOBRO (seobro.com) — a small boutique SEO agency (3 people) specializing in SaaS, Ecommerce, Hotels, and Real Estate. Real results, no vanity metrics.

Write a short cold email to the owner of this website. It must sound like it was written by a real human, not a marketing bot.

Website: {url}
Business niche: {query}
Owner name (if known): {owner}
Contact email: {email}

SEO issues found on their site:
{issues_block}

AI SEO verdict: {verdict}

HUMANIZATION RULES (most important):
- Sound like a real person who actually looked at their site — not a template
- GREETING: If owner name is known, use it naturally (e.g. "Hey John,"). If owner is unknown — use just "Hey," on its own line. NEVER write "Hey Business Owner", "Hi there", "Dear Sir/Madam" or any generic salutation.
- No corporate openers: NEVER use "I hope this email finds you well", "I wanted to reach out", "I came across your website"
- Use contractions naturally: you're, we've, it's, don't, we'd
- Mix short and long sentences — vary the rhythm
- One small genuine observation or compliment about their business before the problem
- Mention 2 SPECIFIC issues by name (e.g. "no meta description", "H1 is missing") — not vague like "SEO problems"
- Max 100 words total for the body
- No bullet points — flowing natural text
- CTA: offer a free SEO audit delivered by email — NO calls, NO meetings
- Do NOT write a sign-off or signature — it will be added automatically
- NEVER mention fake stats or percentages

FORBIDDEN PHRASES:
"I hope", "I wanted to", "I came across", "please don't hesitate", "feel free to",
"at your earliest convenience", "moving forward", "synergy", "leverage", "touch base"

Return ONLY valid JSON, no markdown:
{{
  "subject": "short punchy subject line (not clickbait, not generic)",
  "body": "email body with \\n for line breaks"
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
                owner=owner or "unknown",
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

        SIGNATURE = (
            "\n\n--\n"
            "Best regards,\n\n"
            "Alex\n"
            "Project Manager\n\n"
            "SEO Bro | Search Growth & Visibility\n\n"
            "alex@seobro.com\n"
            "seobro.com"
        )

        data = json.loads(raw)
        return {
            "subject": data.get("subject", ""),
            "body":    data.get("body", "").rstrip() + SIGNATURE,
            "error":   "",
        }

    except Exception as e:
        return {"subject": "", "body": "", "error": str(e)}
