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


NICHE_HINTS = {
    "Ecommerce": (
        "Focus on: more organic product discovery, higher sales without ad spend, "
        "outranking competitor stores. Mention that well-optimised product pages bring "
        "buyers who are ready to purchase — not just browse."
    ),
    "SaaS": (
        "Focus on: more organic trial signups, reducing CAC vs paid ads, "
        "ranking for high-intent keywords that bring users ready to try the product. "
        "Mention that AI tools like ChatGPT now surface well-optimised SaaS tools."
    ),
    "HoReCa": (
        "Focus on: more direct bookings (cutting OTA commission fees), ranking higher "
        "in local and destination searches, appearing in Google Maps top results. "
        "Every direct booking saved from OTA = pure profit."
    ),
    "Real Estate": (
        "Focus on: more property inquiries from organic search, ranking for local "
        "neighbourhood and listing keywords, building trust with buyers/sellers "
        "who research agents online before reaching out."
    ),
    "Local Services": (
        "Focus on: dominating 'near me' and local searches, ranking above competitors "
        "on Google Maps, getting more inbound calls without paying per click."
    ),
    "Healthcare": (
        "Focus on: more patient inquiries from local search, ranking for condition/treatment "
        "keywords, building trust through authoritative content that Google rewards."
    ),
    "Beauty & Wellness": (
        "Focus on: more local bookings from organic search, ranking above competing salons/spas, "
        "appearing in Google Maps when people search for services nearby."
    ),
    "Travel & Tourism": (
        "Focus on: more direct tour/package bookings, ranking for destination keywords, "
        "appearing in AI travel recommendations (ChatGPT, Perplexity) that travellers now use."
    ),
    "Fitness & Sport": (
        "Focus on: more class/membership signups from local search, outranking competing "
        "gyms/studios, appearing when people search for fitness options nearby."
    ),
    "Education": (
        "Focus on: more course enrollments from organic search, ranking for programme "
        "keywords, appearing in AI tools students use to find learning options."
    ),
    "Legal & Finance": (
        "Focus on: more consultation requests, ranking for high-intent legal/financial "
        "keywords, building authority that makes clients trust you before they call."
    ),
}

PROMPT = """\
You are writing a cold outreach email on behalf of SEOBRO (seobro.com) — a boutique SEO agency with a proven track record (one client generated $1M+ in additional organic revenue over 6 years). Small team, real results, no vanity metrics.

Write a short cold email to the owner of this website. It must stand out in a crowded inbox — owners get pitched every day and ignore boring grey messages.

Website: {url}
Business niche: {niche}
Search context: {query}
Owner name (if known): {owner}
Contact email: {email}

SEO issues found on their site:
{issues_block}

AI SEO verdict: {verdict}

NICHE-SPECIFIC ANGLE (tailor your value proposition to this):
{niche_hint}

STYLE RULES:
- Sound like a real person who actually looked at their site — not a template
- GREETING: If owner name is known, use it naturally (e.g. "Hey John,"). If unknown — use just "Hey," on its own line. NEVER write "Hey Business Owner", "Hi there", "Dear Sir/Madam".
- No corporate openers: NEVER use "I hope this email finds you well", "I wanted to reach out", "I came across your website"
- Use contractions naturally: you're, we've, it's, don't, we'd
- Mix short and long sentences — vary the rhythm
- One genuine observation or compliment about their business before the problem

EMOJIS:
- Add 1 relevant emoji to the subject line (not 🚀 or 📈 — too generic)
- Add 2–3 emojis naturally inside the body to highlight key points
- Good examples: 🔍 before a specific SEO issue, 💡 before the value point, ✅ before the CTA
- Don't overdo it — max 3 emojis in body

SOCIAL PROOF (use naturally, don't force it):
- You MAY mention that SEOBRO helped a client generate $1M+ in additional organic revenue — but only if it fits naturally and the business is the right size to relate to that scale
- Keep it brief — one casual mention, not a sales pitch

EXCLUSIVITY TONE (important — builds trust):
- Subtly convey that SEOBRO is selective — they don't take every project, they choose clients they genuinely see potential in
- This is NOT a mass blast — frame it as: "we looked at your site specifically and think there's real opportunity here"
- One natural line that signals selectivity, e.g. "we're quite selective about who we work with" or "we only take on projects where we see clear growth potential" — keep it brief and genuine, not arrogant
- This makes the recipient feel chosen, not spammed

CONTENT RULES:
- Mention 2 SPECIFIC issues by name (e.g. "no meta description", "H1 is missing")
- Max 110 words total for the body
- No bullet points — flowing natural text
- CTA: offer a free SEO audit delivered by email — NO calls, NO meetings
- Do NOT write a sign-off or signature — it will be added automatically
- NEVER mention fake stats or percentages

FORBIDDEN PHRASES:
"I hope", "I wanted to", "I came across", "please don't hesitate", "feel free to",
"at your earliest convenience", "moving forward", "synergy", "leverage", "touch base"

Return ONLY valid JSON, no markdown:
{{
  "subject": "short punchy subject line with 1 emoji",
  "body": "email body with \\n for line breaks"
}}"""


def generate_email(
    url: str,
    query: str,
    issues: list[str],
    verdict: str = "",
    owner: str = "",
    email: str = "",
    niche: str = "",
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
        niche_hint = NICHE_HINTS.get(niche, (
            "Focus on: more organic traffic, outranking competitors, "
            "long-term growth without relying on paid ads."
        ))

        resp = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": PROMPT.format(
                url=url,
                niche=niche or "General business",
                query=query,
                owner=owner or "unknown",
                email=email or "(unknown)",
                issues_block=issues_block,
                verdict=verdict or "(not available)",
                niche_hint=niche_hint,
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
