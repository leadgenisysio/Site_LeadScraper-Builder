"""Flask web application for the lead scraper dashboard."""

import logging
import sys
import time

from flask import Flask, jsonify, render_template, request, Response

from config import (
    ALL_TRADES, LEAD_STATUSES, STATES, TRADES,
    NETLIFY_API_TOKEN, GMAIL_ADDRESS, GMAIL_APP_PASSWORD,
    OUTREACH_DAILY_LIMIT, OUTREACH_SEND_DELAY, OUTREACH_TEST_MODE,
    HOSTING_PLATFORM,
)
from database.models import (
    delete_lead,
    export_leads_csv,
    get_ab_stats,
    get_connection,
    get_lead,
    get_leads,
    get_outreach_log,
    get_stats,
    get_outreach_candidates,
    get_outreach_stats,
    has_been_emailed,
    init_db,
    insert_outreach_log,
    mark_lead_sent,
    update_lead_demo,
    update_lead_demo_approval,
    update_lead_status,
)
from outreach.candidates import score_all_candidates
from outreach.email_sender import (
    can_send_today,
    compose_outreach_email,
    get_remaining_today,
    send_email,
)
from outreach import netlify_deployer, cloudflare_deployer
from outreach.site_generator import generate_demo_site
from scraper.pipeline import get_scrape_status, start_scrape, stop_scrape

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


# ── Hosting platform dispatcher ─────────────────────────────────────
def _use_cloudflare():
    return HOSTING_PLATFORM == "cloudflare" and cloudflare_deployer.is_configured()


def hosting_deploy(business_name, html, images=None):
    """Deploy a demo site using the configured hosting platform."""
    if _use_cloudflare():
        return cloudflare_deployer.deploy_demo_site(business_name, html, images=images)
    return netlify_deployer.deploy_demo_site(business_name, html, images=images)


def hosting_redeploy(site_id, html, images=None):
    """Redeploy to an existing site using the configured hosting platform."""
    if _use_cloudflare():
        return cloudflare_deployer.redeploy_site(site_id, html, images=images)
    return netlify_deployer.redeploy_site(site_id, html, images=images)


def hosting_delete(site_id):
    """Delete a site from the configured hosting platform."""
    if _use_cloudflare():
        return cloudflare_deployer.delete_site(site_id)
    return netlify_deployer.delete_netlify_site(site_id)


def hosting_list():
    """List all sites from the configured hosting platform."""
    if _use_cloudflare():
        return cloudflare_deployer.list_sites()
    return netlify_deployer.list_netlify_sites()


def hosting_configured():
    """Check if any hosting platform is configured."""
    if _use_cloudflare():
        return True
    return bool(NETLIFY_API_TOKEN)

app = Flask(__name__)


# --- Page routes ---

@app.route("/")
def dashboard():
    stats = get_stats()
    return render_template(
        "dashboard.html",
        states=STATES,
        trades=ALL_TRADES,
        statuses=LEAD_STATUSES,
        trade_categories=TRADES,
        stats=stats,
    )


@app.route("/scrape")
def scrape_page():
    return render_template(
        "scrape.html",
        states=STATES,
        trade_categories=TRADES,
    )


@app.route("/outreach")
def outreach_page():
    return render_template("outreach.html")


@app.route("/sites")
def sites_page():
    return render_template("sites.html")


# --- API routes ---

@app.route("/api/leads")
def api_leads():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    leads, total = get_leads(
        state=request.args.get("state"),
        trade=request.args.get("trade"),
        status=request.args.get("status"),
        has_phone=request.args.get("has_phone"),
        has_email=request.args.get("has_email"),
        search=request.args.get("search"),
        page=page,
        per_page=per_page,
    )
    return jsonify({
        "leads": leads,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 1,
    })


@app.route("/api/leads/<int:lead_id>/status", methods=["POST"])
def api_update_status(lead_id):
    data = request.get_json()
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "Missing status"}), 400
    try:
        update_lead_status(lead_id, new_status)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/leads/<int:lead_id>", methods=["DELETE"])
def api_delete_lead(lead_id):
    delete_lead(lead_id)
    return jsonify({"ok": True})


@app.route("/api/export")
def api_export():
    csv_data = export_leads_csv(
        state=request.args.get("state"),
        trade=request.args.get("trade"),
        status=request.args.get("status"),
        has_phone=request.args.get("has_phone"),
        has_email=request.args.get("has_email"),
    )
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@app.route("/api/scrape", methods=["POST"])
def api_start_scrape():
    data = request.get_json()
    states = data.get("states", [])
    trades = data.get("trades", [])
    results_per_query = data.get("results_per_query", 10)

    if not states or not trades:
        return jsonify({"error": "Select at least one state and one trade."}), 400

    ok, msg = start_scrape(trades, states, results_per_query)
    status_code = 200 if ok else 409
    return jsonify({"ok": ok, "message": msg}), status_code


@app.route("/api/scrape/stop", methods=["POST"])
def api_stop_scrape():
    ok, msg = stop_scrape()
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/scrape/status")
def api_scrape_status():
    return jsonify(get_scrape_status())


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


# --- Outreach API routes ---

@app.route("/api/outreach/candidates")
def api_outreach_candidates():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    leads, total = get_outreach_candidates(
        max_score=request.args.get("max_score", 50, type=int),
        state=request.args.get("state"),
        trade=request.args.get("trade"),
        page=page,
        per_page=per_page,
    )
    return jsonify({
        "leads": leads,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 1,
    })


@app.route("/api/outreach/stats")
def api_outreach_stats():
    stats = get_outreach_stats()
    stats["daily_limit"] = OUTREACH_DAILY_LIMIT
    stats["hosting_configured"] = hosting_configured()
    stats["hosting_platform"] = "Cloudflare" if _use_cloudflare() else "Netlify"
    stats["netlify_configured"] = bool(NETLIFY_API_TOKEN)
    stats["gmail_configured"] = bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)
    stats["test_mode"] = OUTREACH_TEST_MODE
    return jsonify(stats)


@app.route("/api/outreach/score", methods=["POST"])
def api_score_candidates():
    try:
        scored = score_all_candidates()
        return jsonify({"ok": True, "scored": scored})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/outreach/<int:lead_id>/generate", methods=["POST"])
def api_generate_demo(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404

    if lead.get("demo_url"):
        return jsonify({"ok": False, "error": "Demo already generated"}), 409

    if not hosting_configured():
        return jsonify({"ok": False, "error": "No hosting platform configured. Set Netlify or Cloudflare credentials in config.py."}), 400

    try:
        result = generate_demo_site(lead)
        html = result["html"]
        images = result.get("images", {})
        site_id, site_url = hosting_deploy(lead["business_name"], html, images=images)
        update_lead_demo(lead_id, site_url, site_id)
        img_count = len(images)
        return jsonify({"ok": True, "demo_url": site_url, "site_id": site_id, "images_generated": img_count})
    except Exception as e:
        logging.error(f"Demo generation failed for lead {lead_id}: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/outreach/<int:lead_id>/redeploy", methods=["POST"])
def api_redeploy_demo(lead_id):
    """Regenerate and redeploy a demo site (fixes broken deploys)."""
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404
    if not lead.get("demo_site_id"):
        return jsonify({"ok": False, "error": "No existing demo to redeploy"}), 400
    if not hosting_configured():
        return jsonify({"ok": False, "error": "No hosting platform configured"}), 400

    try:
        result = generate_demo_site(lead)
        html = result["html"]
        images = result.get("images", {})
        hosting_redeploy(lead["demo_site_id"], html, images=images)
        return jsonify({"ok": True, "demo_url": lead["demo_url"], "images_generated": len(images)})
    except Exception as e:
        logging.error(f"Redeploy failed for lead {lead_id}: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/outreach/<int:lead_id>/approve", methods=["POST"])
def api_approve_demo(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404
    if not lead.get("demo_url"):
        return jsonify({"ok": False, "error": "No demo to approve"}), 400
    update_lead_demo_approval(lead_id, True)
    return jsonify({"ok": True})


@app.route("/api/outreach/<int:lead_id>/reject", methods=["POST"])
def api_reject_demo(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404

    # Delete Netlify site if it exists
    if lead.get("demo_site_id"):
        try:
            hosting_delete(lead["demo_site_id"])
        except Exception as e:
            logging.warning(f"Failed to delete hosted site: {e}")

    # Clear demo fields
    update_lead_demo(lead_id, None, None)
    update_lead_demo_approval(lead_id, False)
    return jsonify({"ok": True})


@app.route("/api/outreach/<int:lead_id>/preview-email")
def api_preview_email(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    if not lead.get("demo_url"):
        return jsonify({"error": "No demo URL — generate a demo first"}), 400

    email_addr = lead.get("email", "")
    if "," in email_addr:
        email_addr = email_addr.split(",")[0].strip()

    variant_id = request.args.get("variant")
    subject, html_body, plain_body, variant_id = compose_outreach_email(lead, lead["demo_url"], variant_id=variant_id)
    return jsonify({
        "to": email_addr,
        "subject": subject,
        "html_body": html_body,
        "plain_body": plain_body,
        "variant_id": variant_id,
    })


@app.route("/api/outreach/<int:lead_id>/send", methods=["POST"])
def api_send_outreach(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found"}), 404

    if not lead.get("demo_approved"):
        return jsonify({"ok": False, "error": "Demo must be approved before sending"}), 400

    if not lead.get("demo_url"):
        return jsonify({"ok": False, "error": "No demo URL"}), 400

    if lead.get("outreach_sent_at"):
        return jsonify({"ok": False, "error": "Already sent to this lead"}), 409

    if not can_send_today(OUTREACH_DAILY_LIMIT):
        return jsonify({"ok": False, "error": "Daily send limit reached"}), 429

    email_addr = lead.get("email", "")
    if "," in email_addr:
        email_addr = email_addr.split(",")[0].strip()

    if not email_addr:
        return jsonify({"ok": False, "error": "No email address"}), 400

    # Check duplicate
    if has_been_emailed(email_addr):
        return jsonify({"ok": False, "error": f"Already sent outreach to {email_addr}"}), 409

    try:
        subject, html_body, plain_body, variant_id = compose_outreach_email(lead, lead["demo_url"])
        send_email(email_addr, subject, html_body, plain_body)
        mark_lead_sent(lead_id)
        insert_outreach_log(lead_id, email_addr, subject, lead["demo_url"], subject_variant=variant_id)
        return jsonify({"ok": True, "variant": variant_id})
    except Exception as e:
        logging.error(f"Send failed for lead {lead_id}: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/outreach/batch-send", methods=["POST"])
def api_batch_send():
    remaining = get_remaining_today(OUTREACH_DAILY_LIMIT)
    if remaining <= 0:
        return jsonify({"ok": False, "sent": 0, "skipped": 0, "error": "Daily limit reached"}), 429

    # Get all approved, unsent leads
    leads, _ = get_outreach_candidates(max_score=100, page=1, per_page=remaining)
    approved = [l for l in leads if l.get("demo_approved") == 1 and not l.get("outreach_sent_at")]

    sent = 0
    skipped = 0
    errors = 0

    for lead in approved:
        if sent >= remaining:
            break

        email_addr = lead.get("email", "")
        if "," in email_addr:
            email_addr = email_addr.split(",")[0].strip()

        if not email_addr or has_been_emailed(email_addr):
            skipped += 1
            continue

        try:
            subject, html_body, plain_body, variant_id = compose_outreach_email(lead, lead["demo_url"])
            send_email(email_addr, subject, html_body, plain_body)
            mark_lead_sent(lead["id"])
            insert_outreach_log(lead["id"], email_addr, subject, lead["demo_url"], subject_variant=variant_id)
            sent += 1

            # Delay between sends
            if sent < len(approved):
                time.sleep(OUTREACH_SEND_DELAY)
        except Exception as e:
            logging.error(f"Batch send failed for lead {lead['id']}: {e}")
            errors += 1

    return jsonify({"ok": True, "sent": sent, "skipped": skipped, "errors": errors})


# --- Sent Email History API ---

@app.route("/api/outreach/sent-log")
def api_sent_log():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    logs, total = get_outreach_log(page=page, per_page=per_page)
    return jsonify({
        "ok": True,
        "logs": logs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 1,
    })


# --- A/B Testing API routes ---

@app.route("/api/outreach/ab-stats")
def api_ab_stats():
    from config import SUBJECT_VARIANTS
    stats = get_ab_stats()
    # Merge with variant definitions so UI knows the subject text
    variant_map = {v["id"]: v["subject"] for v in SUBJECT_VARIANTS} if SUBJECT_VARIANTS else {}
    for s in stats:
        s["subject_template"] = variant_map.get(s["subject_variant"], "(unknown)")
    return jsonify({"ok": True, "variants": stats, "definitions": SUBJECT_VARIANTS or []})


# --- Hosted Sites Management API routes ---

@app.route("/api/hosting/sites")
def api_hosting_sites():
    if not hosting_configured():
        return jsonify({"ok": False, "error": "No hosting platform configured"}), 400
    try:
        sites = hosting_list()
        platform = "Cloudflare" if _use_cloudflare() else "Netlify"
        return jsonify({"ok": True, "sites": sites, "total": len(sites), "platform": platform})
    except Exception as e:
        logging.error(f"Failed to list hosted sites: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# Keep old Netlify endpoint as alias for backwards compatibility
@app.route("/api/netlify/sites")
def api_netlify_sites():
    return api_hosting_sites()


@app.route("/api/hosting/sites/<site_id>", methods=["DELETE"])
@app.route("/api/netlify/sites/<site_id>", methods=["DELETE"])
def api_delete_hosted_site(site_id):
    if not hosting_configured():
        return jsonify({"ok": False, "error": "No hosting platform configured"}), 400
    try:
        hosting_delete(site_id)

        # Also clear demo fields from any lead that used this site
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE leads SET demo_url = NULL, demo_site_id = NULL, demo_approved = 0 "
                "WHERE demo_site_id = ?",
                (site_id,),
            )
            conn.commit()
        finally:
            conn.close()

        return jsonify({"ok": True})
    except Exception as e:
        logging.error(f"Failed to delete Netlify site {site_id}: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5050)
