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

    prompt = f"""You are an elite conversion copywriter who specializes in contractor/home services websites.
You write copy that makes homeowners pick up the phone. Every word earns trust and drives action.

BUSINESS INFO:
- Company: {business_name}
- Trade: {trade}
- State: {state}
- Service Area: {service_area or "local area"}
- Years in Business: {years_in_business or "established"}
- Their Current Tagline: {scraped_tagline or "(none)"}
- Their About Text: {scraped_about[:800] or "(none — write from scratch)"}
- Their Services: {services_text or "(create realistic services for a " + trade.lower() + " company)"}

Generate JSON with these fields. Make EVERY word count — this copy needs to convert:

{{
  "headline": "5-8 word hero headline. Must be specific to {trade}. Reference a concrete benefit or outcome. Examples of GOOD headlines: 'Your Roof. Our Reputation. Zero Worry.' or 'Atlanta's Most Trusted Solar Team Since 2015'. Examples of BAD headlines: 'Quality Service You Can Trust' or 'Professional {trade} Solutions'. Be bold and memorable.",

  "subheadline": "A 10-20 word supporting line under the headline. Add specificity: mention their service area, a key differentiator, or a trust signal like years in business.",

  "about_text": "Write 100-180 words. This must feel PERSONAL, not corporate. Rules: (1) Start with the company name and a specific claim, (2) Mention their service area by name, (3) Include a concrete detail — years in business, number of projects, team size, certifications, (4) End with what makes them different from competitors. If they gave about text, REWRITE it to be more compelling while keeping all factual details. Never say 'we are committed to excellence' or similar filler.",

  "service_descriptions": [
    {{"name": "Service Name", "desc": "20-30 word description. Include a SPECIFIC benefit to the homeowner. Not 'professional installation' but 'Protect your home with Class A materials backed by a 25-year warranty'. Each must be different."}},
    {{"name": "...", "desc": "..."}},
    {{"name": "...", "desc": "..."}},
    {{"name": "...", "desc": "..."}},
    {{"name": "...", "desc": "..."}},
    {{"name": "...", "desc": "..."}}
  ],

  "cta_text": "8-15 word call-to-action. Create soft urgency. Example: 'Schedule your inspection before the next storm season' or 'Get a detailed quote — most respond within 2 hours'. NOT 'Contact us today'.",

  "meta_description": "150-160 char SEO description. Format: '[Company] offers [key services] in [area]. [Trust signal]. [CTA].'",

  "unique_selling_points": [
    "A specific trust signal like 'Licensed & Insured — Policy #XXXXX on file'",
    "A concrete differentiator like 'Same-day emergency response available'",
    "A social proof point like 'Trusted by 500+ {service_area or state} homeowners'",
    "A guarantee like '100% satisfaction guaranteed or we come back at no charge'"
  ]
}}

CRITICAL RULES:
- Use their ACTUAL service names if provided. Create realistic ones otherwise.
- If they gave about text, ENHANCE it — keep the facts, improve the writing.
- NO generic corporate buzzwords. These are LOCAL contractors, not Fortune 500.
- Every description must include a SPECIFIC benefit (time saved, money saved, protection gained, warranty length).
- The unique_selling_points should feel like things posted on a real contractor's truck or yard sign.
- Return ONLY valid JSON. No markdown, no code blocks, no explanation."""

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
