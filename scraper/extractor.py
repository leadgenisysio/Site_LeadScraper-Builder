"""Extract contact information and site content from a webpage.

Also extracts services, about text, colors, tagline, service area,
and years in business to feed into demo site generation.
"""

import json
import logging
import re
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import EXCLUDED_EMAIL_PATTERNS, EXCLUDED_COUNTRY_TLDS, REQUEST_TIMEOUT, USER_AGENT
from scraper.analyzer import analyze_quality

logger = logging.getLogger(__name__)

# Regex for US phone numbers: (xxx) xxx-xxxx, xxx-xxx-xxxx, xxx.xxx.xxxx, xxx xxx xxxx, +1xxxxxxxxxx
PHONE_PATTERN = re.compile(
    r"""
    (?:(?:\+?1[\s.-]?)?              # optional country code
    (?:\(?\d{3}\)?[\s.-]?)           # area code with optional parens
    \d{3}[\s.-]?                     # first 3 digits
    \d{4})                           # last 4 digits
    """,
    re.VERBOSE,
)

# Email regex
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Subpages likely to have contact info
CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/contactus",
    "/about",
    "/about-us",
    "/aboutus",
    "/get-a-quote",
    "/get-quote",
    "/request-quote",
    "/free-estimate",
]

# Subpages likely to have rich content for demo generation
CONTENT_PATHS = [
    "/services", "/our-services", "/what-we-do",
    "/about", "/about-us", "/our-story", "/our-company",
    "/reviews", "/testimonials", "/customer-reviews",
    "/gallery", "/portfolio", "/our-work", "/projects", "/photos",
]

# Link text patterns that suggest a contact/about page
CONTACT_LINK_PATTERNS = re.compile(
    r"\b(contact|about|get.a.quote|free.estimate|reach.us|call.us)\b", re.IGNORECASE
)

# Link text patterns for content-rich subpages
CONTENT_LINK_PATTERNS = re.compile(
    r"\b(services|our services|what we do|about|about us|our story|"
    r"reviews|testimonials|gallery|portfolio|our work|projects|photos)\b",
    re.IGNORECASE,
)


def _normalize_phone(raw):
    """Strip a phone string down to digits and check it's 10 or 11 digits."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _is_valid_email(email):
    """Filter out junk/platform emails and non-US domains."""
    lower = email.lower().strip()
    # Excluded patterns (spam, platform, fake)
    for pattern in EXCLUDED_EMAIL_PATTERNS:
        if pattern in lower:
            return False
    # Filter out image file extensions that regex might catch
    if lower.endswith((".png", ".jpg", ".gif", ".svg", ".webp", ".jpeg")):
        return False
    # Filter out non-US country TLDs
    for tld in EXCLUDED_COUNTRY_TLDS:
        if lower.endswith(tld):
            return False
    return True


def _fetch_page(url):
    """Fetch a URL and return (response, soup) or (None, None) on failure."""
    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        # Only parse HTML responses
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return None, None
        soup = BeautifulSoup(resp.text, "html.parser")
        return resp, soup
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
        return None, None


def _extract_emails_from_soup(soup, raw_html):
    """Extract valid emails from a BeautifulSoup object and raw HTML."""
    emails = set()
    text = soup.get_text(separator=" ", strip=True)

    # From mailto: links
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip()
            if EMAIL_PATTERN.match(email) and _is_valid_email(email):
                emails.add(email.lower())
    # From page text
    for match in EMAIL_PATTERN.findall(text):
        if _is_valid_email(match):
            emails.add(match.lower())
    # Also scan raw HTML for emails (sometimes hidden in attributes)
    for match in EMAIL_PATTERN.findall(raw_html):
        if _is_valid_email(match):
            emails.add(match.lower())

    return emails


def _extract_phones_from_soup(soup):
    """Extract valid phone numbers, preferring visible ones over hidden tel: links."""
    from collections import Counter
    phone_counts = Counter()

    text = soup.get_text(separator=" ", strip=True)

    # From tel: links — ONLY if the link has visible text (skip hidden/tracking links)
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("tel:"):
            link_text = a_tag.get_text(strip=True)
            # Skip hidden tel: links (no visible text, or text doesn't look like a phone)
            if not link_text or len(link_text) < 7:
                continue
            raw_phone = href.replace("tel:", "").strip()
            normalized = _normalize_phone(raw_phone)
            if normalized:
                phone_counts[normalized] += 2  # Weight tel: links higher

    # From visible page text (most reliable — what the user actually sees)
    for match in PHONE_PATTERN.findall(text):
        normalized = _normalize_phone(match)
        if normalized:
            phone_counts[normalized] += 1

    # Return the most frequently appearing phone number(s)
    if not phone_counts:
        return set()

    # Sort by frequency, return top numbers
    sorted_phones = [p for p, _ in phone_counts.most_common(3)]
    return set(sorted_phones)


def _find_contact_page_urls(base_url, soup):
    """Discover contact/about page URLs from the homepage links and common paths."""
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    found = set()

    # Check links on the page that look like contact/about pages
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        link_text = a_tag.get_text(strip=True)

        # Check if the link text suggests contact/about
        if CONTACT_LINK_PATTERNS.search(link_text):
            full_url = urljoin(base_url, href)
            # Only follow links on the same domain
            if urlparse(full_url).netloc == parsed.netloc:
                found.add(full_url)

        # Check if the href path itself matches known contact paths
        href_lower = href.lower()
        for path in CONTACT_PATHS:
            if path in href_lower:
                full_url = urljoin(base_url, href)
                if urlparse(full_url).netloc == parsed.netloc:
                    found.add(full_url)

    # Also try common contact paths directly (in case they exist but aren't linked)
    for path in ["/contact", "/contact-us", "/about"]:
        found.add(base + path)

    # Don't re-fetch the homepage
    found.discard(base_url)
    found.discard(base_url.rstrip("/"))
    found.discard(base + "/")

    return list(found)[:5]  # Limit to 5 subpages max


# ─── Site Content Extraction (for demo generation) ──────────────────

# Headings that indicate services sections
_SERVICES_HEADINGS = re.compile(
    r"\b(services|what we do|our work|capabilities|specialties|specializations|"
    r"our services|we offer|we provide|what we offer)\b",
    re.IGNORECASE,
)

# Headings that indicate about sections
_ABOUT_HEADINGS = re.compile(
    r"\b(about|about us|who we are|our story|our company|our team|"
    r"why choose us|why us|our mission)\b",
    re.IGNORECASE,
)

# Pattern for years in business
_YEARS_PATTERN = re.compile(
    r"(?:since|established|founded|serving since|in business since)\s*(\d{4})",
    re.IGNORECASE,
)
_EXPERIENCE_PATTERN = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|in business|serving)",
    re.IGNORECASE,
)

# Common CSS color pattern (hex colors)
_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{3,6})\b")

# Colors to ignore (too generic: black, white, grays, transparent)
_BORING_COLORS = {
    "000", "000000", "fff", "ffffff", "333", "333333", "666", "666666",
    "999", "999999", "ccc", "cccccc", "eee", "eeeeee", "ddd", "dddddd",
    "f5f5f5", "fafafa", "f0f0f0", "e5e5e5", "aaa", "aaaaaa", "bbb",
    "bbbbbb", "111", "111111", "222", "222222", "444", "444444",
    "555", "555555", "777", "777777", "888", "888888",
}


def _extract_section_text(soup, heading_pattern, max_length=1500):
    """Find a section by heading pattern and extract the text below it."""
    for tag in soup.find_all(re.compile(r"^h[1-4]$", re.IGNORECASE)):
        heading_text = tag.get_text(strip=True)
        if heading_pattern.search(heading_text):
            # Gather sibling text until the next heading
            parts = []
            total_len = 0
            for sibling in tag.find_next_siblings():
                if sibling.name and re.match(r"^h[1-4]$", sibling.name, re.IGNORECASE):
                    break
                text = sibling.get_text(separator=" ", strip=True)
                if text and len(text) > 10:  # skip trivial fragments
                    parts.append(text)
                    total_len += len(text)
                    if total_len > max_length:
                        break
            if parts:
                result = " ".join(parts)
                return result[:max_length]
    return None


def _extract_tagline(soup):
    """Try to find a tagline or slogan from the page."""
    # Check og:description or meta description
    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:description" or meta.get("name") == "description":
            content = meta.get("content", "").strip()
            if 10 < len(content) < 150:
                return content

    # Check first h2 or large text near the top (likely a tagline)
    h1 = soup.find("h1")
    if h1:
        # Look for a subtitle right after the h1
        next_el = h1.find_next_sibling()
        if next_el:
            text = next_el.get_text(strip=True)
            if 10 < len(text) < 150:
                return text

    # Check h2 tags near top of page
    for h2 in soup.find_all("h2"):
        text = h2.get_text(strip=True)
        if 10 < len(text) < 120:
            return text
            break  # just the first one

    return None


def _extract_service_area(soup):
    """Try to find mentioned cities, regions, or service areas."""
    text = soup.get_text(separator=" ", strip=True).lower()

    # Look for "serving [area]" or "service area" patterns
    area_patterns = [
        re.compile(r"serv(?:ing|ice area)\s*[:\-]?\s*(.{10,100}?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"(?:proudly\s+)?serving\s+(.{10,80}?)(?:\.|$)", re.IGNORECASE),
        re.compile(r"service\s+areas?\s*[:\-]?\s*(.{10,100}?)(?:\.|$)", re.IGNORECASE),
    ]
    for pat in area_patterns:
        match = pat.search(soup.get_text(separator=" ", strip=True))
        if match:
            area = match.group(1).strip()
            if len(area) > 5:
                return area[:150]
    return None


def _extract_years_in_business(soup):
    """Extract years of experience or founding year."""
    text = soup.get_text(separator=" ", strip=True)

    # "Since 2005", "Established 1998"
    match = _YEARS_PATTERN.search(text)
    if match:
        return match.group(1)

    # "20+ years of experience"
    match = _EXPERIENCE_PATTERN.search(text)
    if match:
        return f"{match.group(1)}+ years"

    return None


def _extract_primary_color(soup, raw_html):
    """Extract the dominant brand color from CSS/inline styles."""
    colors = Counter()

    # Scan inline styles
    for tag in soup.find_all(style=True):
        style = tag["style"]
        for match in _HEX_COLOR.findall(style):
            c = match.lower()
            if c not in _BORING_COLORS:
                colors[c] += 1

    # Scan <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            for match in _HEX_COLOR.findall(style_tag.string):
                c = match.lower()
                if c not in _BORING_COLORS:
                    colors[c] += 1

    # Scan linked CSS in raw HTML (quick scan, not full CSS parsing)
    for match in _HEX_COLOR.findall(raw_html):
        c = match.lower()
        if c not in _BORING_COLORS:
            colors[c] += 1

    if not colors:
        return None

    # Return the most common non-boring color
    top_color = colors.most_common(1)[0][0]
    # Normalize 3-char to 6-char
    if len(top_color) == 3:
        top_color = "".join(c * 2 for c in top_color)
    return f"#{top_color}"


def _extract_services_list(soup):
    """Try to extract individual service names from lists or cards."""
    services = []

    # Look for service-like lists
    services_section = None
    for tag in soup.find_all(re.compile(r"^h[1-4]$", re.IGNORECASE)):
        if _SERVICES_HEADINGS.search(tag.get_text(strip=True)):
            services_section = tag
            break

    if services_section:
        # Look for list items or divs after the heading
        for sibling in services_section.find_next_siblings():
            if sibling.name and re.match(r"^h[1-4]$", sibling.name, re.IGNORECASE):
                break
            # Check for ul/ol lists
            for li in sibling.find_all("li"):
                text = li.get_text(strip=True)
                if 3 < len(text) < 80:
                    services.append(text)
            # Check for cards/divs with short text (likely service names)
            if not services:
                for div in sibling.find_all(["div", "h3", "h4", "strong"]):
                    text = div.get_text(strip=True)
                    if 3 < len(text) < 60 and not div.find_all(["div", "p"]):
                        services.append(text)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in services:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)

    return unique[:12]  # cap at 12 services


# Headings that indicate testimonials/reviews sections
_REVIEW_HEADINGS = re.compile(
    r"\b(reviews?|testimonials?|what (?:our |)(?:customers?|clients?) say|"
    r"customer feedback|hear from|happy customers|success stories)\b",
    re.IGNORECASE,
)

# Headings that indicate gallery/portfolio sections
_GALLERY_HEADINGS = re.compile(
    r"\b(gallery|portfolio|our work|recent projects|completed projects|"
    r"project gallery|photo gallery|before.+after|our projects|work samples)\b",
    re.IGNORECASE,
)


def _extract_testimonials(soup):
    """Extract customer testimonials/reviews from a page.

    Returns a list of dicts: [{"text": str, "name": str, "rating": int}, ...]
    """
    testimonials = []

    # --- Strategy 1: Direct CSS class matching (most reliable) ---
    # Look for elements with review/testimonial classes ANYWHERE on the page
    review_containers = []
    for el in soup.find_all(["div", "article", "li", "section"]):
        classes = " ".join(el.get("class", []))
        # Match specific review item patterns (not generic containers)
        if re.search(r"one-review|review-item|review-card|testimonial-item|testimonial-card|"
                      r"single-review|single-testimonial|customer-review|review-block",
                      classes, re.IGNORECASE):
            review_containers.append(el)

    # If we found specific review items, extract from those
    if review_containers:
        for el in review_containers:
            # Get review text — look for content div or direct text
            text = ""
            content_div = el.find(class_=re.compile(r"review-content|review-text|testimonial-text|review-body", re.IGNORECASE))
            if content_div:
                text = content_div.get_text(separator=" ", strip=True)
            if not text or len(text) < 20:
                # Fallback: longest text block in the element
                for child in el.find_all(["p", "div", "span"]):
                    t = child.get_text(strip=True)
                    if 20 < len(t) < 500 and len(t) > len(text):
                        text = t
            if not text or len(text) < 20:
                continue

            # Get reviewer name
            name_div = el.find(class_=re.compile(r"review-name|reviewer|author-name|customer-name", re.IGNORECASE))
            name = name_div.get_text(strip=True) if name_div else _find_reviewer_name(el)
            # Clean name (remove date parts like "John A, February 2025")
            if "," in name:
                parts = name.split(",")
                # Keep only the name part (before the date)
                name = parts[0].strip()

            rating = _find_star_rating(el)
            if 20 < len(text) < 500:
                testimonials.append({"text": text, "name": name, "rating": rating})

    # --- Strategy 2: Find reviews section by heading, then search siblings ---
    if not testimonials:
        review_section = None
        for tag in soup.find_all(re.compile(r"^h[1-4]$", re.IGNORECASE)):
            if _REVIEW_HEADINGS.search(tag.get_text(strip=True)):
                review_section = tag
                break

        search_areas = []
        if review_section:
            # Try siblings first
            for sibling in review_section.find_next_siblings():
                if sibling.name and re.match(r"^h[1-4]$", sibling.name, re.IGNORECASE):
                    break
                search_areas.append(sibling)
            # If no siblings had reviews, try the heading's parent container
            if not search_areas:
                parent = review_section.parent
                if parent:
                    search_areas = [parent]
        else:
            search_areas = [soup]

        for area in search_areas:
            # Blockquotes
            for bq in area.find_all("blockquote"):
                text = bq.get_text(separator=" ", strip=True)
                if 20 < len(text) < 500:
                    name = _find_attribution(bq)
                    testimonials.append({"text": text, "name": name, "rating": 5})

            # Divs with review-like classes
            for el in area.find_all(["div", "article", "li", "section"]):
                classes = " ".join(el.get("class", []))
                if re.search(r"review|testimonial|quote|feedback", classes, re.IGNORECASE):
                    paragraphs = el.find_all(["p", "div", "span"])
                    best_text = ""
                    for p in paragraphs:
                        t = p.get_text(strip=True)
                        if 30 < len(t) < 500 and len(t) > len(best_text):
                            best_text = t
                    if best_text:
                        name = _find_reviewer_name(el)
                        rating = _find_star_rating(el)
                        testimonials.append({"text": best_text, "name": name, "rating": rating})

    # --- Strategy 3: Schema.org Review structured data ---
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            reviews = []
            if isinstance(data, dict):
                reviews = data.get("review", [])
                if isinstance(reviews, dict):
                    reviews = [reviews]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        reviews.extend(item.get("review", []) if isinstance(item.get("review"), list) else [item.get("review", {})])
            for rev in reviews:
                if not isinstance(rev, dict):
                    continue
                body = rev.get("reviewBody", rev.get("description", ""))
                author = rev.get("author", {})
                name = author.get("name", "Customer") if isinstance(author, dict) else str(author)
                rating_val = rev.get("reviewRating", {})
                rating = int(rating_val.get("ratingValue", 5)) if isinstance(rating_val, dict) else 5
                if body and 20 < len(body) < 500:
                    testimonials.append({"text": body, "name": name, "rating": rating})
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    # Deduplicate by text similarity (first 50 chars)
    seen = set()
    unique = []
    for t in testimonials:
        key = t["text"][:50].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique[:6]  # Cap at 6 testimonials


def _find_attribution(blockquote):
    """Find a name/attribution near a blockquote."""
    # Check <cite>, <footer>, or next sibling
    cite = blockquote.find(["cite", "footer"])
    if cite:
        text = cite.get_text(strip=True)
        if 2 < len(text) < 60:
            return text.lstrip("—– ").strip()
    # Check next sibling
    nxt = blockquote.find_next_sibling()
    if nxt:
        text = nxt.get_text(strip=True)
        if 2 < len(text) < 50:
            return text.lstrip("—– ").strip()
    return "Happy Customer"


def _find_reviewer_name(element):
    """Find a reviewer name within a review element."""
    # Look for elements with name-like classes
    for el in element.find_all(["span", "p", "div", "strong", "h4", "h5"]):
        classes = " ".join(el.get("class", []))
        if re.search(r"name|author|reviewer|customer|client", classes, re.IGNORECASE):
            text = el.get_text(strip=True)
            if 2 < len(text) < 50:
                return text
    # Look for <cite>
    cite = element.find("cite")
    if cite:
        text = cite.get_text(strip=True)
        if 2 < len(text) < 50:
            return text
    return "Happy Customer"


def _find_star_rating(element):
    """Try to detect a star rating from an element."""
    # Check for aria-label like "5 stars" or "4.5 out of 5"
    for el in element.find_all(True):
        label = el.get("aria-label", "")
        match = re.search(r"(\d(?:\.\d)?)\s*(?:out of \d|stars?|rating)", label, re.IGNORECASE)
        if match:
            return min(5, max(1, round(float(match.group(1)))))
    # Check for star unicode characters
    text = element.get_text()
    stars = text.count("★") + text.count("⭐")
    if 1 <= stars <= 5:
        return stars
    return 5  # Default to 5 stars


def _extract_gallery_images(soup, base_url):
    """Extract portfolio/gallery image URLs from a page.

    Returns a list of absolute image URLs (up to 8).
    """
    images = []
    parsed_base = urlparse(base_url)

    # Strategy 1: Find gallery section by heading
    gallery_section = None
    for tag in soup.find_all(re.compile(r"^h[1-4]$", re.IGNORECASE)):
        if _GALLERY_HEADINGS.search(tag.get_text(strip=True)):
            gallery_section = tag
            break

    search_areas = []
    if gallery_section:
        for sibling in gallery_section.find_next_siblings():
            if sibling.name and re.match(r"^h[1-4]$", sibling.name, re.IGNORECASE):
                break
            search_areas.append(sibling)

    # Strategy 2: Look for gallery-like containers by class
    if not search_areas:
        for el in soup.find_all(["div", "section", "ul"]):
            classes = " ".join(el.get("class", []))
            if re.search(r"gallery|portfolio|project|lightbox|masonry|grid", classes, re.IGNORECASE):
                search_areas.append(el)

    for area in search_areas:
        for img in area.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            if not src or src.startswith("data:"):
                continue
            # Make absolute
            abs_url = urljoin(base_url, src)
            # Filter: must be same domain, reasonably sized, not icons/logos
            img_parsed = urlparse(abs_url)
            if img_parsed.netloc and img_parsed.netloc != parsed_base.netloc:
                # Allow common CDN patterns
                if not any(cdn in img_parsed.netloc for cdn in ["wp.com", "cloudinary", "imgix", "amazonaws"]):
                    continue
            # Skip tiny images (likely icons)
            width = img.get("width", "")
            height = img.get("height", "")
            try:
                if width and int(width) < 100:
                    continue
                if height and int(height) < 100:
                    continue
            except ValueError:
                pass
            # Skip common non-photo patterns
            lower_src = abs_url.lower()
            if any(skip in lower_src for skip in ["logo", "icon", "favicon", "placeholder", "loading", "spinner", "avatar"]):
                continue
            images.append(abs_url)

    # Deduplicate
    seen = set()
    unique = []
    for url in images:
        if url not in seen:
            seen.add(url)
            unique.append(url)

    return unique[:8]


def _extract_service_descriptions(soup):
    """Extract services with descriptions (not just names).

    Returns a list of dicts: [{"name": str, "desc": str}, ...]
    """
    services = []

    # Find services section
    services_section = None
    for tag in soup.find_all(re.compile(r"^h[1-4]$", re.IGNORECASE)):
        if _SERVICES_HEADINGS.search(tag.get_text(strip=True)):
            services_section = tag
            break

    if not services_section:
        return []

    # Look for service cards/items after the heading
    for sibling in services_section.find_next_siblings():
        if sibling.name and re.match(r"^h[1-4]$", sibling.name, re.IGNORECASE):
            # Could be a sub-heading for a service
            sub_heading = sibling.get_text(strip=True)
            if 3 < len(sub_heading) < 80:
                # Get the description text after this sub-heading
                desc_parts = []
                for desc_sib in sibling.find_next_siblings():
                    if desc_sib.name and re.match(r"^h[1-4]$", desc_sib.name, re.IGNORECASE):
                        break
                    text = desc_sib.get_text(separator=" ", strip=True)
                    if text and len(text) > 10:
                        desc_parts.append(text)
                        break  # Just first paragraph
                desc = desc_parts[0][:200] if desc_parts else ""
                services.append({"name": sub_heading, "desc": desc})
            continue

        # Look for cards/divs with h3/h4 titles and paragraph descriptions
        for card in sibling.find_all(["div", "article", "li"]):
            title_el = card.find(["h3", "h4", "h5", "strong"])
            if not title_el:
                continue
            name = title_el.get_text(strip=True)
            if not (3 < len(name) < 80):
                continue
            # Find description paragraph
            desc = ""
            p_el = card.find("p")
            if p_el:
                desc = p_el.get_text(separator=" ", strip=True)[:200]
            if not desc:
                # Try all text minus the title
                full_text = card.get_text(separator=" ", strip=True)
                remainder = full_text.replace(name, "", 1).strip()
                if len(remainder) > 15:
                    desc = remainder[:200]
            services.append({"name": name, "desc": desc})

    # Deduplicate by name
    seen = set()
    unique = []
    for s in services:
        key = s["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:12]


def _find_content_page_urls(base_url, soup):
    """Discover content-rich subpage URLs (services, about, reviews, gallery)."""
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    found = set()

    # Check links on the page
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        link_text = a_tag.get_text(strip=True)

        if CONTENT_LINK_PATTERNS.search(link_text):
            full_url = urljoin(base_url, href)
            if urlparse(full_url).netloc == parsed.netloc:
                found.add(full_url)

        href_lower = href.lower()
        for path in CONTENT_PATHS:
            if path in href_lower:
                full_url = urljoin(base_url, href)
                if urlparse(full_url).netloc == parsed.netloc:
                    found.add(full_url)

    # Try common content paths directly
    for path in ["/services", "/about", "/reviews", "/testimonials", "/gallery", "/portfolio"]:
        found.add(base + path)

    # Remove homepage
    found.discard(base_url)
    found.discard(base_url.rstrip("/"))
    found.discard(base + "/")

    return list(found)[:8]


def _extract_logo_url(soup, base_url):
    """Try to find the site's logo image URL."""
    parsed = urlparse(base_url)

    # Strategy 1: Look for <img> with logo-related attributes
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        alt = img.get("alt", "").lower()
        classes = " ".join(img.get("class", [])).lower()
        img_id = (img.get("id") or "").lower()
        parent_classes = " ".join(img.parent.get("class", [])).lower() if img.parent else ""

        if any(kw in (src.lower() + " " + alt + " " + classes + " " + img_id + " " + parent_classes)
               for kw in ["logo", "brand", "site-logo", "header-logo", "navbar-logo"]):
            if src and not src.startswith("data:"):
                abs_url = urljoin(base_url, src)
                return abs_url

    # Strategy 2: Check <link rel="icon"> for a high-res favicon/icon
    for link in soup.find_all("link", rel=True):
        rels = link.get("rel", [])
        if isinstance(rels, str):
            rels = [rels]
        if any(r in ["apple-touch-icon", "icon"] for r in rels):
            href = link.get("href", "")
            sizes = link.get("sizes", "")
            # Prefer larger icons (apple-touch-icon is usually 180x180)
            if href and "apple-touch-icon" in rels:
                return urljoin(base_url, href)

    return None


def _extract_certifications(soup):
    """Extract certifications, accreditations, and industry badges.

    Returns a list of certification/badge names found on the page.
    """
    text = soup.get_text(separator=" ", strip=True)
    text_lower = text.lower()

    # Known certification/accreditation patterns for contractors
    CERT_PATTERNS = {
        # Roofing
        "GAF Master Elite": r"gaf\s*master\s*elite",
        "GAF Certified": r"gaf\s*certif",
        "Owens Corning Preferred": r"owens\s*corning\s*prefer",
        "CertainTeed SELECT": r"certainteed\s*select",
        "HAAG Certified": r"haag\s*certif",
        # Solar
        "NABCEP Certified": r"nabcep",
        "Tesla Powerwall Certified": r"tesla\s*powerwall\s*certif",
        "SunPower Elite Dealer": r"sunpower\s*elite",
        "Enphase Installer": r"enphase\s*(?:certif|install|partner)",
        # General
        "BBB Accredited": r"bbb\s*accredit|better\s*business\s*bureau",
        "BBB A+ Rating": r"bbb\s*a\+|a\+\s*(?:rated|rating)\s*(?:with\s*)?bbb",
        "Home Advisor": r"home\s*advisor|homeadvisor",
        "Angi Certified": r"angi\s*certif|angie.s?\s*list",
        "EPA Certified": r"epa\s*certif|epa\s*lead",
        "OSHA Certified": r"osha\s*(?:certif|compli|train)",
        "NATE Certified": r"nate\s*certif",  # HVAC
        "Energy Star Partner": r"energy\s*star\s*partner",
        "LEED Certified": r"leed\s*(?:certif|accred)",
        # Insurance/licensing
        "Fully Licensed": r"fully\s*licensed",
        "Fully Insured": r"fully\s*insured",
        "Bonded": r"(?:fully\s*)?bonded",
    }

    found = []
    for cert_name, pattern in CERT_PATTERNS.items():
        if re.search(pattern, text_lower):
            found.append(cert_name)

    return found[:8]


def _extract_brands(soup):
    """Extract brand/manufacturer partnerships mentioned on the page.

    Returns a list of brand names.
    """
    text = soup.get_text(separator=" ", strip=True)
    text_lower = text.lower()

    BRAND_PATTERNS = {
        # Roofing materials
        "GAF": r"\bgaf\b",
        "Owens Corning": r"owens\s*corning",
        "CertainTeed": r"certainteed",
        "Tamko": r"\btamko\b",
        "IKO": r"\biko\b",
        "Atlas Roofing": r"atlas\s*roofing",
        # Solar
        "SunPower": r"sunpower",
        "Enphase": r"enphase",
        "Tesla Solar": r"tesla\s*(?:solar|powerwall)",
        "SolarEdge": r"solaredge",
        "LG Solar": r"lg\s*solar",
        "Panasonic Solar": r"panasonic\s*(?:solar|evergreen)",
        "Generac": r"\bgenerac\b",
        # HVAC
        "Carrier": r"\bcarrier\b",
        "Trane": r"\btrane\b",
        "Lennox": r"\blennox\b",
        "Rheem": r"\brheem\b",
        "Goodman": r"\bgoodman\b",
        "Daikin": r"\bdaikin\b",
        "Mitsubishi Electric": r"mitsubishi\s*electric",
        # Plumbing
        "Rinnai": r"\brinnai\b",
        "Navien": r"\bnavien\b",
        "Bradford White": r"bradford\s*white",
        # General
        "Home Depot": r"home\s*depot",
        "Lowe's": r"\blowe.?s\b",
    }

    found = []
    for brand_name, pattern in BRAND_PATTERNS.items():
        if re.search(pattern, text_lower):
            found.append(brand_name)

    return found[:6]


def _extract_social_links(soup, base_url):
    """Extract social media profile URLs."""
    social_domains = {
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "twitter": "twitter.com",
        "x": "x.com",
        "linkedin": "linkedin.com",
        "youtube": "youtube.com",
        "tiktok": "tiktok.com",
        "yelp": "yelp.com",
        "nextdoor": "nextdoor.com",
        "google": "google.com/maps",
    }

    found = {}
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].lower()
        for platform, domain in social_domains.items():
            if domain in href and platform not in found:
                found[platform] = a_tag["href"]

    return found


def _extract_aggregate_rating(soup):
    """Extract aggregate review rating from Schema.org JSON-LD data.

    Returns dict with keys: rating, review_count, or empty dict.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                agg = item.get("aggregateRating")
                if isinstance(agg, dict):
                    rating = agg.get("ratingValue")
                    count = agg.get("reviewCount") or agg.get("ratingCount")
                    if rating:
                        return {
                            "rating": str(rating),
                            "review_count": str(count) if count else "",
                        }
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def _extract_business_hours(soup):
    """Extract business hours from the page."""
    text = soup.get_text(separator=" ", strip=True)

    # Look for common patterns
    hours_patterns = [
        re.compile(r"(?:hours|schedule|open)\s*:?\s*((?:mon|tue|wed|thu|fri|sat|sun).{10,80})", re.IGNORECASE),
        re.compile(r"((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*[-–:]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm).{5,60})", re.IGNORECASE),
        re.compile(r"((?:M-F|Mon-Fri|Monday-Friday)\s*:?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))", re.IGNORECASE),
    ]

    for pattern in hours_patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()[:100]

    # Check for 24/7
    if re.search(r"24\s*/?\s*7|twenty.four.seven|24\s*hours?\s*(?:a\s*day|service)", text, re.IGNORECASE):
        return "24/7 Emergency Service Available"

    return ""


def _extract_site_content(soup, raw_html, base_url=""):
    """Extract structured content from a webpage for demo site generation.

    Returns a dict with all extractable content fields.
    """
    return {
        "services_text": _extract_section_text(soup, _SERVICES_HEADINGS),
        "about_text": _extract_section_text(soup, _ABOUT_HEADINGS),
        "tagline": _extract_tagline(soup),
        "service_area": _extract_service_area(soup),
        "primary_color": _extract_primary_color(soup, raw_html),
        "years_in_business": _extract_years_in_business(soup),
        "services_list": _extract_services_list(soup),
        "services_with_desc": _extract_service_descriptions(soup),
        "testimonials": _extract_testimonials(soup),
        "gallery_images": _extract_gallery_images(soup, base_url),
        "logo_url": _extract_logo_url(soup, base_url),
        "certifications": _extract_certifications(soup),
        "brands": _extract_brands(soup),
        "social_links": _extract_social_links(soup, base_url),
        "aggregate_rating": _extract_aggregate_rating(soup),
        "business_hours": _extract_business_hours(soup),
    }


def _merge_site_content(primary, secondary):
    """Merge content from a subpage into the primary content dict.

    Subpage data fills in gaps — it never overwrites existing data.
    Lists (testimonials, gallery_images) are extended.
    """
    for key in ("services_text", "about_text", "tagline", "service_area",
                "primary_color", "years_in_business", "logo_url",
                "business_hours"):
        if not primary.get(key) and secondary.get(key):
            primary[key] = secondary[key]

    # Extend list fields
    if secondary.get("services_list"):
        existing = set(s.lower() for s in primary.get("services_list", []))
        for s in secondary["services_list"]:
            if s.lower() not in existing and len(primary.get("services_list", [])) < 12:
                primary.setdefault("services_list", []).append(s)
                existing.add(s.lower())

    if secondary.get("services_with_desc"):
        existing = set(s["name"].lower() for s in primary.get("services_with_desc", []))
        for s in secondary["services_with_desc"]:
            if s["name"].lower() not in existing and len(primary.get("services_with_desc", [])) < 12:
                primary.setdefault("services_with_desc", []).append(s)
                existing.add(s["name"].lower())

    if secondary.get("testimonials"):
        existing = set(t["text"][:50].lower() for t in primary.get("testimonials", []))
        for t in secondary["testimonials"]:
            if t["text"][:50].lower() not in existing and len(primary.get("testimonials", [])) < 6:
                primary.setdefault("testimonials", []).append(t)
                existing.add(t["text"][:50].lower())

    if secondary.get("gallery_images"):
        existing = set(primary.get("gallery_images", []))
        for url in secondary["gallery_images"]:
            if url not in existing and len(primary.get("gallery_images", [])) < 8:
                primary.setdefault("gallery_images", []).append(url)
                existing.add(url)

    # Merge certifications and brands (deduplicate)
    for key in ("certifications", "brands"):
        if secondary.get(key):
            existing = set(x.lower() for x in primary.get(key, []))
            for item in secondary[key]:
                if item.lower() not in existing:
                    primary.setdefault(key, []).append(item)
                    existing.add(item.lower())

    # Merge social links (don't overwrite)
    if secondary.get("social_links"):
        for platform, url in secondary["social_links"].items():
            if platform not in primary.get("social_links", {}):
                primary.setdefault("social_links", {})[platform] = url

    # Merge aggregate rating (prefer one with review count)
    if secondary.get("aggregate_rating") and not primary.get("aggregate_rating"):
        primary["aggregate_rating"] = secondary["aggregate_rating"]

    return primary


def extract_contact_info(url):
    """
    Fetch a URL and extract contact information + site content.

    Also crawls likely contact/about pages on the same site to maximize
    the chance of finding emails and phone numbers.

    Returns a dict with:
        business_name, emails (list), phones (list), url,
        quality_*, site_content (dict)
    Returns None if the page couldn't be fetched.
    """
    resp, soup = _fetch_page(url)
    if resp is None:
        logger.warning(f"Could not fetch homepage: {url}")
        return None

    text = soup.get_text(separator=" ", strip=True)

    # --- Business name ---
    business_name = None
    # Try og:site_name
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        business_name = og["content"].strip()
    # Fallback to <title> — pick the best segment
    if not business_name and soup.title and soup.title.string:
        raw_title = soup.title.string.strip()
        parts = re.split(r"\s*[|\u2013\u2014]\s*", raw_title)
        if len(parts) == 1:
            parts = re.split(r"\s*-\s*", raw_title)
        # Filter out generic segments (locations, "Home", service descriptions)
        _generic = re.compile(
            r"^(home|welcome|official|best|top|find|#?\d|solar panel install|"
            r"residential|commercial|services? in|contractor in|near me)",
            re.IGNORECASE,
        )
        candidates = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2
                       and not _generic.match(p.strip())]
        if candidates:
            # Prefer shorter, title-case-looking segments (likely the actual business name)
            candidates.sort(key=lambda c: (len(c) > 50, not any(w[0].isupper() for w in c.split() if w), len(c)))
            business_name = candidates[0]
        else:
            business_name = parts[0].strip()
    # Fallback to first <h1>
    if not business_name:
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            if len(h1_text) < 80:  # Skip overly long H1s (likely descriptions)
                business_name = h1_text
    # Fallback to domain name (clean up TLD)
    if not business_name:
        domain = urlparse(url).netloc.replace("www.", "")
        # Try to make domain look like a name: "acmeroofing.com" → "Acmeroofing"
        business_name = domain.split(".")[0].title()

    # --- Extract from homepage ---
    emails = _extract_emails_from_soup(soup, resp.text)
    phones = _extract_phones_from_soup(soup)

    # --- Crawl contact/about pages for more contact info ---
    if not emails or not phones:
        subpage_urls = _find_contact_page_urls(url, soup)
        for sub_url in subpage_urls:
            if emails and phones:
                break  # Already found both, stop crawling
            sub_resp, sub_soup = _fetch_page(sub_url)
            if sub_resp is None:
                continue
            logger.debug(f"  Checking subpage: {sub_url}")
            new_emails = _extract_emails_from_soup(sub_soup, sub_resp.text)
            new_phones = _extract_phones_from_soup(sub_soup)
            emails.update(new_emails)
            phones.update(new_phones)

    # --- Quality analysis (based on homepage) ---
    quality = analyze_quality(url, resp, soup)

    # --- Site content extraction (homepage first) ---
    site_content = _extract_site_content(soup, resp.text, base_url=url)

    # --- Crawl content-rich subpages (services, about, reviews, gallery) ---
    content_urls = _find_content_page_urls(url, soup)
    pages_crawled = 0
    for sub_url in content_urls:
        if pages_crawled >= 5:
            break
        sub_resp, sub_soup = _fetch_page(sub_url)
        if sub_resp is None:
            continue
        pages_crawled += 1
        logger.debug(f"  Extracting content from subpage: {sub_url}")
        sub_content = _extract_site_content(sub_soup, sub_resp.text, base_url=sub_url)
        _merge_site_content(site_content, sub_content)

        # Also grab contact info from content pages while we're there
        if not emails:
            emails.update(_extract_emails_from_soup(sub_soup, sub_resp.text))
        if not phones:
            phones.update(_extract_phones_from_soup(sub_soup))

    logger.info(
        "Content extracted: %d services, %d testimonials, %d gallery images",
        len(site_content.get("services_list", [])),
        len(site_content.get("testimonials", [])),
        len(site_content.get("gallery_images", [])),
    )

    return {
        "business_name": business_name[:200] if business_name else None,
        "emails": list(emails),
        "phones": list(phones),
        "url": url,
        "quality_score": quality["score"],
        "quality_grade": quality["grade"],
        "quality_issues": quality["issues"],
        "is_dead": quality.get("is_dead", False),
        "site_content": site_content,
    }
