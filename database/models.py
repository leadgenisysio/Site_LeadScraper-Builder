"""SQLite database layer for lead storage."""

import csv
import io
import json
import sqlite3
from datetime import datetime, date

from config import DATABASE_PATH, LEAD_STATUSES

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name TEXT,
    website TEXT UNIQUE,
    email TEXT,
    phone TEXT,
    state TEXT,
    trade TEXT,
    source_query TEXT,
    scraped_at TEXT,
    status TEXT DEFAULT 'new',
    quality_score INTEGER,
    quality_grade TEXT,
    quality_issues TEXT
)
"""

_CREATE_OUTREACH_LOG = """
CREATE TABLE IF NOT EXISTS outreach_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    email_to TEXT NOT NULL,
    email_subject TEXT,
    demo_url TEXT,
    status TEXT DEFAULT 'sent',
    FOREIGN KEY (lead_id) REFERENCES leads(id)
)
"""

# Columns added after initial schema — ALTER TABLE for existing DBs
_MIGRATIONS = [
    "ALTER TABLE leads ADD COLUMN quality_score INTEGER",
    "ALTER TABLE leads ADD COLUMN quality_grade TEXT",
    "ALTER TABLE leads ADD COLUMN quality_issues TEXT",
    # Outreach columns
    "ALTER TABLE leads ADD COLUMN site_content TEXT",
    "ALTER TABLE leads ADD COLUMN demo_url TEXT",
    "ALTER TABLE leads ADD COLUMN demo_site_id TEXT",
    "ALTER TABLE leads ADD COLUMN demo_approved INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN outreach_sent_at TEXT",
    "ALTER TABLE leads ADD COLUMN outreach_score INTEGER",
    "ALTER TABLE leads ADD COLUMN is_dead INTEGER DEFAULT 0",
    "ALTER TABLE outreach_log ADD COLUMN subject_variant TEXT",
]


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_OUTREACH_LOG)
    for migration in _MIGRATIONS:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


def insert_lead(business_name, website, email, phone, state, trade, source_query,
                quality_score=None, quality_grade=None, quality_issues=None,
                site_content=None, is_dead=False):
    """Insert a lead, skipping if the website URL already exists."""
    content_json = json.dumps(site_content) if site_content else None
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO leads
               (business_name, website, email, phone, state, trade, source_query,
                scraped_at, status, quality_score, quality_grade, quality_issues,
                site_content, is_dead)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                business_name,
                website,
                email,
                phone,
                state,
                trade,
                source_query,
                datetime.now().isoformat(),
                "new",
                quality_score,
                quality_grade,
                quality_issues,
                content_json,
                1 if is_dead else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_lead(lead_id):
    """Get a single lead by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if row:
        lead = dict(row)
        if lead.get("site_content"):
            try:
                lead["site_content"] = json.loads(lead["site_content"])
            except (json.JSONDecodeError, TypeError):
                lead["site_content"] = {}
        return lead
    return None


def get_leads(state=None, trade=None, status=None, has_phone=None, has_email=None,
              search=None, page=1, per_page=50):
    """Get leads with optional filters. Returns (leads_list, total_count)."""
    conn = get_connection()
    conditions = []
    params = []

    if state:
        conditions.append("state = ?")
        params.append(state)
    if trade:
        conditions.append("trade = ?")
        params.append(trade)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if has_phone == "yes":
        conditions.append("phone IS NOT NULL AND phone != ''")
    elif has_phone == "no":
        conditions.append("(phone IS NULL OR phone = '')")
    if has_email == "yes":
        conditions.append("email IS NOT NULL AND email != ''")
    elif has_email == "no":
        conditions.append("(email IS NULL OR email = '')")
    if search:
        conditions.append("(business_name LIKE ? OR website LIKE ? OR email LIKE ? OR phone LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term] * 4)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    # Get total count
    count_row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM leads{where_clause}", params
    ).fetchone()
    total = count_row["cnt"]

    # Get paginated results
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM leads{where_clause} ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    conn.close()
    return [dict(row) for row in rows], total


def update_lead_status(lead_id, new_status):
    """Update a lead's status."""
    if new_status not in LEAD_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    conn = get_connection()
    conn.execute("UPDATE leads SET status = ? WHERE id = ?", (new_status, lead_id))
    conn.commit()
    conn.close()


def delete_lead(lead_id):
    conn = get_connection()
    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()


def export_leads_csv(state=None, trade=None, status=None, has_phone=None, has_email=None):
    """Export filtered leads as CSV string."""
    leads, _ = get_leads(
        state=state, trade=trade, status=status,
        has_phone=has_phone, has_email=has_email,
        page=1, per_page=999999,
    )
    output = io.StringIO()
    if not leads:
        output.write("No leads found.\n")
        return output.getvalue()

    writer = csv.DictWriter(output, fieldnames=leads[0].keys())
    writer.writeheader()
    writer.writerows(leads)
    return output.getvalue()


def get_stats():
    """Get summary statistics."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM leads").fetchone()["c"]
    with_phone = conn.execute(
        "SELECT COUNT(*) as c FROM leads WHERE phone IS NOT NULL AND phone != ''"
    ).fetchone()["c"]
    with_email = conn.execute(
        "SELECT COUNT(*) as c FROM leads WHERE email IS NOT NULL AND email != ''"
    ).fetchone()["c"]
    by_state = conn.execute(
        "SELECT state, COUNT(*) as c FROM leads GROUP BY state ORDER BY c DESC"
    ).fetchall()
    by_status = conn.execute(
        "SELECT status, COUNT(*) as c FROM leads GROUP BY status ORDER BY c DESC"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "with_phone": with_phone,
        "with_email": with_email,
        "by_state": {row["state"]: row["c"] for row in by_state},
        "by_status": {row["status"]: row["c"] for row in by_status},
    }


# ─── Outreach Functions ──────────────────────────────────────────────

def update_lead_demo(lead_id, demo_url, demo_site_id):
    """Set the demo URL and Netlify site ID for a lead."""
    conn = get_connection()
    conn.execute(
        "UPDATE leads SET demo_url = ?, demo_site_id = ? WHERE id = ?",
        (demo_url, demo_site_id, lead_id),
    )
    conn.commit()
    conn.close()


def update_lead_demo_approval(lead_id, approved):
    """Approve or reject a demo (1=approved, 0=rejected/pending)."""
    conn = get_connection()
    conn.execute(
        "UPDATE leads SET demo_approved = ? WHERE id = ?",
        (1 if approved else 0, lead_id),
    )
    conn.commit()
    conn.close()


def update_lead_outreach_score(lead_id, score):
    """Set the computed outreach score for a lead."""
    conn = get_connection()
    conn.execute(
        "UPDATE leads SET outreach_score = ? WHERE id = ?",
        (score, lead_id),
    )
    conn.commit()
    conn.close()


def mark_lead_sent(lead_id):
    """Mark a lead as contacted after email is sent."""
    conn = get_connection()
    conn.execute(
        "UPDATE leads SET status = 'contacted', outreach_sent_at = ? WHERE id = ?",
        (datetime.now().isoformat(), lead_id),
    )
    conn.commit()
    conn.close()


def insert_outreach_log(lead_id, email_to, email_subject, demo_url, subject_variant=None):
    """Log an outreach email send."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO outreach_log (lead_id, sent_at, email_to, email_subject, demo_url, subject_variant)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (lead_id, datetime.now().isoformat(), email_to, email_subject, demo_url, subject_variant),
    )
    conn.commit()
    conn.close()


def get_ab_stats():
    """Get A/B test statistics grouped by subject variant."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT subject_variant, COUNT(*) as sent
           FROM outreach_log
           WHERE subject_variant IS NOT NULL
           GROUP BY subject_variant
           ORDER BY subject_variant"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sent_today_count():
    """Count emails sent today."""
    conn = get_connection()
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log WHERE sent_at >= ?",
        (today,),
    ).fetchone()
    conn.close()
    return row["c"]


def has_been_emailed(email_address):
    """Check if an email address has already been sent outreach."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log WHERE email_to = ?",
        (email_address.lower(),),
    ).fetchone()
    conn.close()
    return row["c"] > 0


def get_outreach_log(page=1, per_page=50):
    """Get the sent email history, newest first.

    Returns (list[dict], total_count).
    Each dict has: id, lead_id, sent_at, email_to, email_subject,
    demo_url, status, subject_variant, business_name, trade.
    """
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM outreach_log").fetchone()["c"]
    offset = (page - 1) * per_page
    rows = conn.execute(
        """SELECT ol.*, l.business_name, l.trade, l.state
           FROM outreach_log ol
           LEFT JOIN leads l ON ol.lead_id = l.id
           ORDER BY ol.sent_at DESC
           LIMIT ? OFFSET ?""",
        (per_page, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def get_outreach_candidates(max_score=100, state=None, trade=None, page=1, per_page=50):
    """
    Get leads eligible for outreach, sorted by outreach_score DESC.
    Criteria: has email, status='new', not already sent, quality_score exists.
    """
    conn = get_connection()
    conditions = [
        "email IS NOT NULL AND email != ''",
        "status = 'new'",
        "outreach_sent_at IS NULL",
        "quality_score IS NOT NULL",
        "quality_score <= ?",
        "(is_dead IS NULL OR is_dead = 0)",
    ]
    params = [max_score]

    if state:
        conditions.append("state = ?")
        params.append(state)
    if trade:
        conditions.append("trade = ?")
        params.append(trade)

    where = " WHERE " + " AND ".join(conditions)

    total = conn.execute(
        f"SELECT COUNT(*) as c FROM leads{where}", params
    ).fetchone()["c"]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT * FROM leads{where}
            ORDER BY outreach_score DESC NULLS LAST, quality_score ASC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    conn.close()
    return [dict(row) for row in rows], total


def get_outreach_stats():
    """Get outreach-specific statistics."""
    conn = get_connection()
    today = date.today().isoformat()

    candidates = conn.execute(
        """SELECT COUNT(*) as c FROM leads
           WHERE email IS NOT NULL AND email != ''
           AND status = 'new' AND outreach_sent_at IS NULL
           AND quality_score IS NOT NULL
           AND (is_dead IS NULL OR is_dead = 0)"""
    ).fetchone()["c"]

    demos_generated = conn.execute(
        "SELECT COUNT(*) as c FROM leads WHERE demo_url IS NOT NULL"
    ).fetchone()["c"]

    demos_approved = conn.execute(
        "SELECT COUNT(*) as c FROM leads WHERE demo_approved = 1 AND outreach_sent_at IS NULL"
    ).fetchone()["c"]

    sent_today = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log WHERE sent_at >= ?",
        (today,),
    ).fetchone()["c"]

    sent_total = conn.execute(
        "SELECT COUNT(*) as c FROM outreach_log"
    ).fetchone()["c"]

    conn.close()
    return {
        "candidates": candidates,
        "demos_generated": demos_generated,
        "demos_approved": demos_approved,
        "sent_today": sent_today,
        "sent_total": sent_total,
    }
