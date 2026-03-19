"""Compose and send outreach emails via Gmail SMTP."""

import logging
import random
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    GMAIL_ADDRESS,
    GMAIL_APP_PASSWORD,
    SMTP_HOST,
    SMTP_PORT,
    SENDER_NAME,
    SENDER_COMPANY,
    SENDER_PHONE,
    SENDER_EMAIL,
    SENDER_WEBSITE,
    SENDER_CALENDAR,
    SUBJECT_VARIANTS,
    OUTREACH_TEST_MODE,
    STATES,
)
from database.models import get_sent_today_count

logger = logging.getLogger(__name__)

# ─── Issue Priority (higher = more compelling to mention) ────────────

ISSUE_PRIORITY = {
    "no https": 9,
    "no viewport meta tag": 9,
    "very slow load time": 8,
    "html frames": 10,
    "deprecated html tags": 8,
    "flash": 10,
    "site appears abandoned": 9,
    "html tables for layout": 8,
    "not recently updated": 7,
    "missing or empty title tag": 6,
    "no h1 heading": 5,
    "slow load time": 6,
    "missing meta description": 5,
    "very little text content": 6,
    "thin page content": 4,
    "excessive inline styles": 4,
    "images missing alt text": 4,
    "no structured data": 3,
    "no social media links": 2,
    "no open graph tags": 2,
    "no favicon": 2,
    "built with": 1,
}

# ─── Plain-English Descriptions for Emails ──────────────────────────

ISSUE_DESCRIPTIONS = {
    "no https": (
        "Your site doesn't have SSL security, so visitors see a "
        "'Not Secure' warning in their browser"
    ),
    "no viewport meta tag": (
        "Your website isn't optimized for mobile phones -- it looks "
        "broken or tiny on smartphones"
    ),
    "very slow load time": (
        "Your site takes a long time to load, which causes most "
        "visitors to leave before it finishes"
    ),
    "html frames": (
        "Your site uses technology from the early 2000s that doesn't "
        "work on modern devices"
    ),
    "deprecated html tags": (
        "Your site's code is extremely outdated and hasn't been "
        "modernized in years"
    ),
    "flash": (
        "Your site still uses Flash, which no longer works in any "
        "modern web browser"
    ),
    "site appears abandoned": (
        "Your site's copyright date suggests it hasn't been updated "
        "in over 5 years"
    ),
    "html tables for layout": (
        "Your site uses outdated layout techniques that break on "
        "mobile devices"
    ),
    "not recently updated": (
        "Your site doesn't appear to have been updated in several years"
    ),
    "missing or empty title tag": (
        "Your site doesn't have a proper title, making it harder to "
        "find on Google"
    ),
    "slow load time": (
        "Your site loads slower than recommended, which can hurt your "
        "Google ranking"
    ),
    "missing meta description": (
        "Your site is missing key information that helps it appear in "
        "Google searches"
    ),
    "very little text content": (
        "Your site has very little content, making it hard for "
        "customers to find you online"
    ),
    "no structured data": (
        "Your site is missing data that helps Google show your business "
        "info in search results"
    ),
}


# ─── Helpers ─────────────────────────────────────────────────────────

def _pick_top_issues(quality_issues_str, max_issues=3):
    """Return the top *max_issues* plain-english issue descriptions.

    *quality_issues_str* is a semicolon-separated string produced by the
    analyzer (e.g. ``"No HTTPS; Slow load time (4.2 s); No favicon"``).

    Each raw issue is matched against ``ISSUE_PRIORITY`` using
    case-insensitive substring matching (the same approach the dashboard
    uses).  Issues are sorted by priority descending and the top
    *max_issues* are returned as plain-english strings from
    ``ISSUE_DESCRIPTIONS``.  If a raw issue has no mapping, the raw text
    itself is used as a fallback.
    """
    if not quality_issues_str:
        return []

    raw_issues = [i.strip() for i in quality_issues_str.split(";") if i.strip()]

    scored = []
    for raw in raw_issues:
        raw_lower = raw.lower()
        best_key = None
        best_priority = 0
        for key, priority in ISSUE_PRIORITY.items():
            if key in raw_lower:
                if priority > best_priority:
                    best_priority = priority
                    best_key = key
        description = ISSUE_DESCRIPTIONS.get(best_key, raw) if best_key else raw
        scored.append((best_priority, description))

    # Sort by priority descending, then take the top N
    scored.sort(key=lambda x: x[0], reverse=True)
    return [desc for _, desc in scored[:max_issues]]


def _state_full_name(abbr):
    """Resolve a state abbreviation to its full name."""
    if not abbr:
        return ""
    return STATES.get(abbr.upper(), abbr)


# ─── Compose ─────────────────────────────────────────────────────────

def compose_outreach_email(lead, demo_url, variant_id=None):
    """Build the outreach email for *lead*.

    Parameters
    ----------
    lead : dict
        A lead row from the database (must contain at least
        ``business_name``, ``trade``, ``state``, ``quality_issues``).
    demo_url : str
        The public URL of the deployed demo site.
    variant_id : str or None
        Force a specific A/B variant ID. If ``None``, picks one randomly.

    Returns
    -------
    tuple[str, str, str, str]
        ``(subject, html_body, plain_body, variant_id)``
    """
    biz = lead.get("business_name", "your business")
    trade = lead.get("trade", "contractor")
    state_abbr = lead.get("state", "")
    state_name = _state_full_name(state_abbr)
    issues_str = lead.get("quality_issues", "")

    # ── A/B subject line selection ────────────────────────────────────
    if SUBJECT_VARIANTS:
        if variant_id:
            variant = next((v for v in SUBJECT_VARIANTS if v["id"] == variant_id), None)
        else:
            variant = random.choice(SUBJECT_VARIANTS)
        if variant:
            variant_id = variant["id"]
            subject = variant["subject"].format(
                biz=biz, trade=trade, state=state_name
            )
        else:
            variant_id = "A"
            subject = f"{biz} - I built you a free website mockup"
    else:
        variant_id = "A"
        subject = f"{biz} - I built you a free website mockup"

    # Pick the most impactful issues to mention
    top_issues = _pick_top_issues(issues_str, max_issues=3)

    # ── HTML bullets ────────────────────────────────────────────────
    issue_bullets_html = ""
    for issue in top_issues:
        issue_bullets_html += (
            f'<li style="margin-bottom:8px;color:#555555;'
            f'font-size:15px;line-height:1.5;">{issue}</li>\n'
        )

    # ── Plain-text bullets ──────────────────────────────────────────
    issue_bullets_plain = ""
    for issue in top_issues:
        issue_bullets_plain += f"  - {issue}\n"

    # ── Signature pieces ────────────────────────────────────────────
    sig_parts_plain = []
    if SENDER_NAME:
        sig_parts_plain.append(SENDER_NAME)
    if SENDER_COMPANY:
        sig_parts_plain.append(SENDER_COMPANY)
    if SENDER_PHONE:
        sig_parts_plain.append(SENDER_PHONE)
    if SENDER_WEBSITE:
        sig_parts_plain.append(SENDER_WEBSITE)

    # HTML signature with clickable website link
    sig_html_parts = []
    if SENDER_NAME:
        sig_html_parts.append(
            f'<span style="color:#333333;font-size:14px;font-weight:bold;">{SENDER_NAME}</span>'
        )
    if SENDER_COMPANY:
        sig_html_parts.append(
            f'<span style="color:#555555;font-size:14px;">{SENDER_COMPANY}</span>'
        )
    if SENDER_PHONE:
        sig_html_parts.append(
            f'<span style="color:#555555;font-size:14px;">{SENDER_PHONE}</span>'
        )
    if SENDER_WEBSITE:
        sig_html_parts.append(
            f'<a href="{SENDER_WEBSITE}" style="color:#2563eb;font-size:14px;text-decoration:none;">{SENDER_WEBSITE}</a>'
        )

    sig_html = "<br>".join(sig_html_parts)
    sig_plain = "\n".join(sig_parts_plain)

    # ── HTML body ───────────────────────────────────────────────────
    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f4;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f4f4f4;">
<tr><td align="center" style="padding:30px 10px;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;">

<!-- Body -->
<tr><td style="padding:35px 40px 10px 40px;">
  <p style="margin:0 0 20px 0;color:#333333;font-size:15px;line-height:1.6;">Hi there,</p>

  <p style="margin:0 0 15px 0;color:#333333;font-size:15px;line-height:1.6;">
    I came across {biz}'s website while looking for {trade} services in {state_name}, and I noticed a few things that might be holding you back from getting more customers:
  </p>

  <ul style="margin:0 0 20px 0;padding-left:20px;">
{issue_bullets_html}  </ul>

  <p style="margin:0 0 25px 0;color:#333333;font-size:15px;line-height:1.6;">
    I put together a rough demo of what a redesigned website could look like for {biz} — take a look:
  </p>
</td></tr>

<!-- CTA Button -->
<tr><td align="center" style="padding:0 40px 20px 40px;">
  <table cellpadding="0" cellspacing="0" border="0">
  <tr><td align="center" style="background-color:#2563eb;border-radius:6px;">
    <a href="{demo_url}" target="_blank"
       style="display:inline-block;padding:14px 36px;color:#ffffff;font-size:16px;font-weight:bold;text-decoration:none;font-family:Arial,sans-serif;">
      See Your Website Demo
    </a>
  </td></tr>
  </table>
</td></tr>

<!-- Closing -->
<tr><td style="padding:0 40px 30px 40px;">
  <p style="margin:0 0 20px 0;color:#333333;font-size:15px;line-height:1.6;">
    This is just a rough concept to show what's possible — the real thing would be fully customized to your brand. If you're interested in seeing what a finished version could look like, just reply to this email{f' or <a href="{SENDER_CALENDAR}" style="color:#2563eb;text-decoration:none;font-weight:bold;">book a quick call here</a>' if SENDER_CALENDAR else ''}.
  </p>

  <p style="margin:0 0 5px 0;color:#333333;font-size:15px;line-height:1.6;">Best,</p>
  {sig_html}
</td></tr>

<!-- Unsubscribe footer -->
<tr><td style="padding:20px 40px;border-top:1px solid #eeeeee;">
  <p style="margin:0 0 8px 0;color:#999999;font-size:12px;line-height:1.5;">
    If you'd prefer not to receive messages like this, simply reply with 'unsubscribe' and I'll remove you from my list.
  </p>
  {'<p style="margin:0;color:#aaaaaa;font-size:11px;">Sent by <a href="' + SENDER_WEBSITE + '" style="color:#999999;">' + SENDER_COMPANY + '</a></p>' if SENDER_WEBSITE and SENDER_COMPANY else ''}
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    # ── Plain-text body ─────────────────────────────────────────────
    plain_body = f"""\
Hi there,

I came across {biz}'s website while looking for {trade} services in {state_name}, and I noticed a few things that might be holding you back from getting more customers:

{issue_bullets_plain}
I put together a rough demo of what a redesigned website could look like for {biz} -- take a look:

{demo_url}

This is just a rough concept to show what's possible -- the real thing would be fully customized to your brand. If you're interested in seeing what a finished version could look like, just reply to this email{f" or book a quick call: {SENDER_CALENDAR}" if SENDER_CALENDAR else ""}.

Best,
{sig_plain}

---
If you'd prefer not to receive messages like this, simply reply with 'unsubscribe' and I'll remove you from my list.
{f"Sent by {SENDER_COMPANY} - {SENDER_WEBSITE}" if SENDER_WEBSITE else ""}
"""

    return subject, html_body, plain_body, variant_id


# ─── Send ────────────────────────────────────────────────────────────

def send_email(to_address, subject, html_body, plain_body):
    """Send an email via Gmail SMTP.

    When ``OUTREACH_TEST_MODE`` is ``True`` the *to_address* is replaced
    with ``GMAIL_ADDRESS`` so nothing goes to a real lead.

    Returns ``True`` on success; raises on failure.
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise ValueError(
            "Gmail credentials not configured. Set GMAIL_ADDRESS and "
            "GMAIL_APP_PASSWORD in config.py."
        )

    if OUTREACH_TEST_MODE:
        logger.info(
            "TEST MODE: redirecting email from %s to %s",
            to_address,
            GMAIL_ADDRESS,
        )
        to_address = GMAIL_ADDRESS

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = to_address

    if SENDER_NAME:
        msg["From"] = f"{SENDER_NAME} <{GMAIL_ADDRESS}>"
    else:
        msg["From"] = GMAIL_ADDRESS

    msg["Reply-To"] = SENDER_EMAIL if SENDER_EMAIL else GMAIL_ADDRESS

    # Attach plain-text first, then HTML (email clients prefer the last part)
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    logger.info("Connecting to %s:%s ...", SMTP_HOST, SMTP_PORT)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_address], msg.as_string())

    logger.info("Email sent to %s (subject: %s)", to_address, subject)
    return True


# ─── Rate-Limit Helpers ──────────────────────────────────────────────

def can_send_today(daily_limit):
    """Return ``True`` if the number of emails sent today is below *daily_limit*."""
    return get_sent_today_count() < daily_limit


def get_remaining_today(daily_limit):
    """Return how many more emails can be sent today."""
    return max(0, daily_limit - get_sent_today_count())
