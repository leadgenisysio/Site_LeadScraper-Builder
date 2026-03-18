"""AI-powered content writer using Gemini to generate unique website copy.

Takes scraped content as a seed and produces premium, personalized marketing
copy that makes every demo site read differently.
"""

import json
import logging

from config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(GOOGLE_API_KEY)


def _call_gemini(prompt: str) -> str | None:
    """Call Gemini text model and return the response text."""
    if not GOOGLE_API_KEY:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=GOOGLE_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.error("Gemini text generation failed: %s", e)
        return None


def enhance_site_content(
    business_name: str,
    trade: str,
    state: str,
    scraped_about: str = "",
    scraped_services: list = None,
    scraped_tagline: str = "",
    service_area: str = "",
    years_in_business: str = "",
) -> dict:
    """Use AI to generate unique, premium website copy for a business.

    Returns a dict with keys:
        headline, about_text, service_descriptions, cta_text, meta_description
    Returns empty dict if AI is not configured or fails.
    """
    if not is_configured():
        return {}

    services_text = ""
    if scraped_services:
        names = [s["name"] if isinstance(s, dict) else s for s in scraped_services[:6]]
        services_text = ", ".join(names)

    prompt = f"""You are a premium website copywriter for contractor businesses. Write unique,
compelling marketing copy for this business. Be specific, professional, and conversion-focused.
Do NOT use generic filler — write like you know this business personally.

BUSINESS INFO:
- Name: {business_name}
- Trade: {trade}
- State: {state}
- Service Area: {service_area or "local area"}
- Years in Business: {years_in_business or "established"}
- Their Current Tagline: {scraped_tagline or "(none)"}
- Their Current About Text: {scraped_about[:500] or "(none provided)"}
- Their Services: {services_text or "(general " + trade.lower() + " services)"}

Generate the following in valid JSON format (no markdown, no code blocks, just raw JSON):
{{
  "headline": "A bold, compelling 5-10 word headline for the hero section. Make it powerful and specific to their trade. No generic slogans.",
  "about_text": "A 2-3 sentence about paragraph (80-150 words). Reference their specific trade, years of experience if known, and service area. Sound authentic and trustworthy, not salesy. If they provided about text, rewrite it to be more compelling while keeping the key facts.",
  "service_descriptions": [
    {{"name": "Service 1 Name", "desc": "A unique 15-25 word description that sounds specific and professional"}},
    {{"name": "Service 2 Name", "desc": "Another unique description"}},
    {{"name": "Service 3 Name", "desc": "Another unique description"}},
    {{"name": "Service 4 Name", "desc": "Another unique description"}},
    {{"name": "Service 5 Name", "desc": "Another unique description"}},
    {{"name": "Service 6 Name", "desc": "Another unique description"}}
  ],
  "cta_text": "A compelling 8-15 word call-to-action for the contact section. Create urgency without being pushy.",
  "meta_description": "A 150-160 character SEO meta description for the page. Include the business name, trade, and location."
}}

IMPORTANT RULES:
- Use their actual service names if provided, otherwise create realistic ones for their trade
- If they gave about text, ENHANCE it — don't replace it with generic copy
- The headline should be memorable and trade-specific, not "Quality You Can Trust" generic nonsense
- Sound human, not corporate. These are local contractors, not Fortune 500 companies
- Return ONLY the JSON object, nothing else"""

    logger.info("Generating AI copy for %s (%s)", business_name, trade)
    raw = _call_gemini(prompt)

    if not raw:
        return {}

    # Parse the JSON response
    try:
        # Strip markdown code block markers if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        result = json.loads(cleaned)
        logger.info("AI copy generated successfully for %s", business_name)
        return result
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse AI copy response: %s", e)
        logger.debug("Raw response: %s", raw[:300])
        return {}
