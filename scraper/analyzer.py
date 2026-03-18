"""Website quality analyzer — scores contractor sites and flags specific issues."""

import re
from datetime import datetime
from urllib.parse import urlparse


def analyze_quality(url, resp, soup):
    """
    Analyze a website's quality based on its response and parsed HTML.

    Args:
        url: The website URL
        resp: The requests Response object
        soup: The BeautifulSoup parsed HTML

    Returns:
        dict with:
            score (int): 0-100 where 0=terrible, 100=great
            grade (str): F/D/C/B/A letter grade
            issues (list[str]): Human-readable list of problems found
    """
    issues = []
    score = 100

    html = resp.text
    text = soup.get_text(separator=" ", strip=True)
    parsed_url = urlparse(url)

    # ── SSL / HTTPS ──────────────────────────────────────────────────
    if parsed_url.scheme != "https":
        issues.append("No HTTPS - site is insecure")
        score -= 15

    # ── Response time ────────────────────────────────────────────────
    elapsed = resp.elapsed.total_seconds()
    if elapsed > 5:
        issues.append(f"Very slow load time ({elapsed:.1f}s)")
        score -= 12
    elif elapsed > 3:
        issues.append(f"Slow load time ({elapsed:.1f}s)")
        score -= 6

    # ── Mobile responsiveness ────────────────────────────────────────
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        issues.append("No viewport meta tag - not mobile friendly")
        score -= 15

    # ── Meta description ─────────────────────────────────────────────
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        issues.append("Missing meta description - poor SEO")
        score -= 8

    # ── Title tag ────────────────────────────────────────────────────
    if not soup.title or not soup.title.string or not soup.title.string.strip():
        issues.append("Missing or empty title tag")
        score -= 8

    # ── Heading structure ────────────────────────────────────────────
    h1_tags = soup.find_all("h1")
    if len(h1_tags) == 0:
        issues.append("No H1 heading on page")
        score -= 5
    elif len(h1_tags) > 3:
        issues.append(f"Too many H1 tags ({len(h1_tags)}) - poor structure")
        score -= 3

    # ── Favicon ──────────────────────────────────────────────────────
    favicon = (
        soup.find("link", rel="icon")
        or soup.find("link", rel="shortcut icon")
        or soup.find("link", rel=re.compile(r"icon", re.I))
    )
    if not favicon:
        issues.append("No favicon")
        score -= 3

    # ── Images without alt text ──────────────────────────────────────
    images = soup.find_all("img")
    if images:
        no_alt = sum(1 for img in images if not img.get("alt", "").strip())
        if no_alt > 0:
            pct = int((no_alt / len(images)) * 100)
            if pct > 50:
                issues.append(f"{no_alt}/{len(images)} images missing alt text - bad accessibility")
                score -= 8
            elif pct > 20:
                issues.append(f"{no_alt}/{len(images)} images missing alt text")
                score -= 4

    # ── Outdated HTML patterns ───────────────────────────────────────
    # Tables used for layout
    tables = soup.find_all("table")
    layout_tables = [t for t in tables if not t.find_parent("table") and len(t.find_all("td")) > 4]
    if len(layout_tables) > 2:
        issues.append("Uses HTML tables for layout - outdated design")
        score -= 10

    # Font tags, center tags, marquee — signs of ancient HTML
    old_tags = len(soup.find_all(["font", "center", "marquee", "blink", "bgsound"]))
    if old_tags > 0:
        issues.append(f"Uses deprecated HTML tags ({old_tags} found) - very outdated code")
        score -= 12

    # Frames / iframes for layout
    frames = soup.find_all(["frame", "frameset"])
    if frames:
        issues.append("Uses HTML frames - extremely outdated")
        score -= 15

    # ── Flash / outdated tech ────────────────────────────────────────
    flash_refs = soup.find_all(["embed", "object"])
    flash_found = any(
        "flash" in str(tag).lower() or ".swf" in str(tag).lower()
        for tag in flash_refs
    )
    if flash_found:
        issues.append("Uses Flash - obsolete technology")
        score -= 15

    # ── Inline styles (excessive) ────────────────────────────────────
    inline_styled = soup.find_all(attrs={"style": True})
    if len(inline_styled) > 20:
        issues.append(f"Excessive inline styles ({len(inline_styled)} elements) - poor code quality")
        score -= 8
    elif len(inline_styled) > 10:
        issues.append(f"Heavy use of inline styles ({len(inline_styled)} elements)")
        score -= 4

    # ── Copyright year check ─────────────────────────────────────────
    current_year = datetime.now().year
    copyright_match = re.search(
        r'(?:©|\bcopyright\b)[^\d]*(\d{4})', html.lower()
    )
    if copyright_match:
        year = int(copyright_match.group(1))
        age = current_year - year
        if age >= 5:
            issues.append(f"Copyright year is {year} - site appears abandoned ({age}+ years old)")
            score -= 12
        elif age >= 3:
            issues.append(f"Copyright year is {year} - not recently updated")
            score -= 6

    # ── Page content amount ──────────────────────────────────────────
    word_count = len(text.split())
    if word_count < 50:
        issues.append("Very little text content on page")
        score -= 8
    elif word_count < 150:
        issues.append("Thin page content")
        score -= 4

    # ── No structured data ───────────────────────────────────────────
    has_schema = "schema.org" in html or "application/ld+json" in html
    if not has_schema:
        issues.append("No structured data (schema.org) - poor SEO")
        score -= 5

    # ── Builder detection (template sites — not custom, but not terrible) ─
    builder = _detect_builder(html, soup)
    if builder:
        issues.append(f"Built with {builder} - template site, not custom")
        # Don't penalize too hard, templates aren't "broken"
        score -= 2

    # ── No social media links ────────────────────────────────────────
    social_domains = ["facebook.com", "instagram.com", "twitter.com", "x.com",
                      "linkedin.com", "youtube.com", "tiktok.com"]
    links = soup.find_all("a", href=True)
    has_social = any(
        any(sd in link["href"] for sd in social_domains)
        for link in links
    )
    if not has_social:
        issues.append("No social media links found")
        score -= 3

    # ── Open Graph tags ──────────────────────────────────────────────
    og_tags = soup.find_all("meta", property=re.compile(r"^og:"))
    if not og_tags:
        issues.append("No Open Graph tags - links won't preview well on social media")
        score -= 3

    # ── Dead / inactive business detection ─────────────────────────────
    is_dead = _detect_dead_business(html, text, soup, issues)

    # Clamp score
    score = max(0, min(100, score))

    # Letter grade
    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "issues": issues,
        "is_dead": is_dead,
    }


def _detect_dead_business(html, text, soup, issues):
    """Detect if a business appears to be dead, closed, or the domain is parked.

    Returns True if the business should be EXCLUDED from outreach.
    Appends a reason to ``issues`` if dead.
    """
    text_lower = text.lower()
    html_lower = html.lower()

    # ── Explicitly closed ─────────────────────────────────────────────
    closed_phrases = [
        "permanently closed",
        "no longer in business",
        "out of business",
        "closed permanently",
        "we have closed",
        "we are closed",
        "business is closed",
        "this business has closed",
        "no longer operating",
        "ceased operations",
        "shutting down",
        "has shut down",
        "we are no longer",
        "no longer accepting",
        "retired from business",
    ]
    for phrase in closed_phrases:
        if phrase in text_lower:
            issues.append(f"DEAD BUSINESS — '{phrase}' found on site")
            return True

    # ── Domain parked / for sale ──────────────────────────────────────
    parked_phrases = [
        "this domain is for sale",
        "domain is parked",
        "this website is for sale",
        "domain for sale",
        "buy this domain",
        "this domain may be for sale",
        "domain name for sale",
        "parked by",
        "parked domain",
        "domain parking",
        "this page is parked",
        "godaddy domain parking",
        "hugedomains",
        "sedoparking",
        "afternic",
        "dan.com",
    ]
    for phrase in parked_phrases:
        if phrase in text_lower or phrase in html_lower:
            issues.append(f"DEAD BUSINESS — domain parked/for sale ('{phrase}')")
            return True

    # ── Coming soon / under construction with NO real content ─────────
    placeholder_phrases = [
        "coming soon",
        "under construction",
        "website under development",
        "site under construction",
        "launching soon",
        "check back soon",
        "stay tuned",
    ]
    word_count = len(text.split())
    if word_count < 80:  # Very little content
        for phrase in placeholder_phrases:
            if phrase in text_lower:
                issues.append(f"DEAD BUSINESS — placeholder page ('{phrase}', only {word_count} words)")
                return True

    # ── Abandoned: very old copyright + very thin content ─────────────
    current_year = datetime.now().year
    copyright_match = re.search(r'(?:©|\bcopyright\b)[^\d]*(\d{4})', html_lower)
    if copyright_match:
        year = int(copyright_match.group(1))
        age = current_year - year
        if age >= 7 and word_count < 200:
            issues.append(f"DEAD BUSINESS — copyright {year} ({age} years old) with very thin content")
            return True

    # ── Generic/empty default pages ───────────────────────────────────
    if word_count < 20:
        issues.append(f"DEAD BUSINESS — virtually empty page (only {word_count} words)")
        return True

    # ── Hosting default pages ─────────────────────────────────────────
    hosting_defaults = [
        "your website is ready",
        "welcome to your new site",
        "this is a default page",
        "default web page",
        "it works!",
        "apache2 default page",
        "welcome to nginx",
        "index of /",
        "congratulations! your site is live",
        "website coming soon",
        "future home of",
    ]
    for phrase in hosting_defaults:
        if phrase in text_lower:
            issues.append(f"DEAD BUSINESS — hosting default page ('{phrase}')")
            return True

    return False


def _detect_builder(html, soup):
    """Try to identify the website builder/CMS."""
    html_lower = html.lower()

    # WordPress
    if "wp-content" in html_lower or "wp-includes" in html_lower:
        return "WordPress"

    # Wix
    meta_gen = soup.find("meta", attrs={"name": "generator"})
    gen_content = meta_gen.get("content", "").lower() if meta_gen else ""

    if "wix.com" in html_lower or "wix" in gen_content:
        return "Wix"

    # Squarespace
    if "squarespace" in html_lower or "squarespace" in gen_content:
        return "Squarespace"

    # Weebly
    if "weebly" in html_lower:
        return "Weebly"

    # GoDaddy Website Builder
    if "godaddy" in html_lower and ("website-builder" in html_lower or "wsb" in html_lower):
        return "GoDaddy Builder"

    # Joomla
    if "joomla" in gen_content:
        return "Joomla"

    # Drupal
    if "drupal" in html_lower or "drupal" in gen_content:
        return "Drupal"

    return None
