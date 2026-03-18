"""Intelligent candidate scoring for outreach.

Computes a composite outreach score (0-100) for each lead based on
quality deficiencies, contact availability, issue severity, content
richness, and trade value.  Higher scores indicate better outreach
candidates.
"""

import json

from config import HIGH_VALUE_TRADES
from database.models import get_connection, update_lead_outreach_score


# ── Scoring weights ──────────────────────────────────────────────────

_WEIGHT_QUALITY = 0.35       # 35 pts max
_WEIGHT_HAS_PHONE = 10       # 10 pts flat
_WEIGHT_ISSUE_SEVERITY = 25  # 25 pts cap
_WEIGHT_CONTENT = 15         # 15 pts cap (3 per populated field)
_WEIGHT_TRADE_HIGH = 15      # 15 pts for high-value trades
_WEIGHT_TRADE_DEFAULT = 8    #  8 pts for all other trades

# Fields in site_content that contribute to the content-richness score
_CONTENT_FIELDS = [
    "services_text",
    "about_text",
    "tagline",
    "service_area",
    "primary_color",
]


# ── Helpers ──────────────────────────────────────────────────────────

def _score_quality(quality_score):
    """Lower quality_score means the site is worse -> higher outreach value."""
    if quality_score is None:
        return 0
    return round((100 - quality_score) * _WEIGHT_QUALITY)


def _score_has_phone(phone):
    """10 pts if the lead has a phone number on file."""
    if phone and str(phone).strip():
        return _WEIGHT_HAS_PHONE
    return 0


def _score_issue_severity(quality_issues):
    """Score based on high-impact issues found in the quality_issues string."""
    if not quality_issues:
        return 0

    issues_lower = quality_issues.lower()
    pts = 0

    if "no https" in issues_lower:
        pts += 5
    if "no viewport" in issues_lower or "not mobile" in issues_lower:
        pts += 5
    if "abandoned" in issues_lower or "frames" in issues_lower or "flash" in issues_lower:
        pts += 5
    if "deprecated" in issues_lower:
        pts += 4
    if "slow load" in issues_lower:
        pts += 3
    if "tables for layout" in issues_lower:
        pts += 3

    return min(pts, _WEIGHT_ISSUE_SEVERITY)


def _score_content_richness(site_content):
    """Score based on how many content fields are populated."""
    if not site_content:
        return 0

    # site_content may arrive as a JSON string or already-parsed dict
    if isinstance(site_content, str):
        try:
            site_content = json.loads(site_content)
        except (json.JSONDecodeError, TypeError):
            return 0

    if not isinstance(site_content, dict):
        return 0

    populated = 0
    for field in _CONTENT_FIELDS:
        value = site_content.get(field)
        if value and str(value).strip():
            populated += 1

    return min(populated * 3, _WEIGHT_CONTENT)


def _score_trade_value(trade):
    """High-value trades receive a scoring bonus."""
    if trade and trade in HIGH_VALUE_TRADES:
        return _WEIGHT_TRADE_HIGH
    return _WEIGHT_TRADE_DEFAULT


# ── Public API ───────────────────────────────────────────────────────

def compute_outreach_score(lead):
    """Compute a composite outreach score (0-100) for a single lead dict.

    Parameters
    ----------
    lead : dict
        A lead row dictionary with at least the keys ``quality_score``,
        ``phone``, ``quality_issues``, ``site_content``, and ``trade``.

    Returns
    -------
    int
        An integer score between 0 and 100 (inclusive).
    """
    score = 0
    score += _score_quality(lead.get("quality_score"))
    score += _score_has_phone(lead.get("phone"))
    score += _score_issue_severity(lead.get("quality_issues"))
    score += _score_content_richness(lead.get("site_content"))
    score += _score_trade_value(lead.get("trade"))

    # Clamp to 0-100
    return max(0, min(score, 100))


def score_all_candidates():
    """Score every eligible lead and persist the results.

    Eligible leads satisfy **all** of the following:
    * has a non-empty email address
    * status is ``'new'``
    * ``quality_score`` is not NULL
    * ``outreach_sent_at`` is NULL (not yet contacted)

    Each lead's composite score is written back to the database via
    :func:`database.models.update_lead_outreach_score`.

    Returns
    -------
    int
        The number of leads that were scored.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM leads
               WHERE email IS NOT NULL AND email != ''
                 AND status = 'new'
                 AND quality_score IS NOT NULL
                 AND outreach_sent_at IS NULL
                 AND (is_dead IS NULL OR is_dead = 0)"""
        ).fetchall()
    finally:
        conn.close()

    scored = 0
    for row in rows:
        lead = dict(row)
        # Parse site_content from JSON string if necessary
        if lead.get("site_content") and isinstance(lead["site_content"], str):
            try:
                lead["site_content"] = json.loads(lead["site_content"])
            except (json.JSONDecodeError, TypeError):
                lead["site_content"] = {}

        score = compute_outreach_score(lead)
        update_lead_outreach_score(lead["id"], score)
        scored += 1

    return scored
