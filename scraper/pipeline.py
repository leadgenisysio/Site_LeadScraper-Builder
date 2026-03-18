"""Orchestrates the full scraping pipeline: search -> extract -> store."""

import logging
import threading
import time

from config import STATES
from database.models import insert_lead
from scraper.extractor import extract_contact_info
from scraper.search import search_contractors

logger = logging.getLogger(__name__)


class ScrapeJob:
    """Tracks a running scrape job's progress and state."""

    def __init__(self):
        self.running = False
        self.progress = 0
        self.total = 0
        self.current_query = ""
        self.leads_found = 0
        self.urls_checked = 0
        self.phase = "idle"  # idle, scraping, done, error
        self.error = None
        self._stop_event = threading.Event()

    @property
    def status(self):
        return {
            "running": self.running,
            "phase": self.phase,
            "progress": self.progress,
            "total": self.total,
            "current_query": self.current_query,
            "leads_found": self.leads_found,
            "urls_checked": self.urls_checked,
            "error": self.error,
        }

    def stop(self):
        self._stop_event.set()

    @property
    def should_stop(self):
        return self._stop_event.is_set()


# Global job tracker (single job at a time)
current_job = ScrapeJob()


def _extract_and_store(url, state, trade, query, job, seen_urls):
    """Extract contact info from a URL and store it if valid."""
    if url in seen_urls:
        return
    seen_urls.add(url)

    job.urls_checked += 1
    job.current_query = url

    info = extract_contact_info(url)
    if info is None:
        return

    email_str = ", ".join(info["emails"]) if info["emails"] else None
    phone_str = ", ".join(info["phones"]) if info["phones"] else None

    if email_str or phone_str:
        issues_str = "; ".join(info.get("quality_issues", []))
        insert_lead(
            business_name=info["business_name"],
            website=url,
            email=email_str,
            phone=phone_str,
            state=state,
            trade=trade,
            source_query=query,
            quality_score=info.get("quality_score"),
            quality_grade=info.get("quality_grade"),
            quality_issues=issues_str or None,
            site_content=info.get("site_content"),
            is_dead=info.get("is_dead", False),
        )
        job.leads_found += 1
        logger.info(
            f"  Lead: {info['business_name']} | "
            f"Phone: {phone_str} | Email: {email_str} | "
            f"Quality: {info.get('quality_grade', '?')} ({info.get('quality_score', '?')})"
        )


def _run_pipeline(trades, states, results_per_query):
    """
    Run the full pipeline in a background thread.

    Searches and extracts per trade+state combo so leads appear immediately
    instead of waiting for all searches to finish first.
    """
    global current_job
    job = current_job

    try:
        job.running = True
        job.phase = "scraping"
        job.leads_found = 0
        job.urls_checked = 0
        job.error = None
        job.total = len(trades) * len(states)
        job.progress = 0

        seen_urls = set()

        for state in states:
            for trade in trades:
                if job.should_stop:
                    break

                job.progress += 1
                state_name = STATES.get(state, state)
                job.current_query = f"Searching: {trade} in {state_name}"
                logger.info(f"--- {trade} in {state_name} ({job.progress}/{job.total}) ---")

                # Search for URLs for this combo
                urls = search_contractors(trade, state, results_per_query)

                if job.should_stop:
                    break

                # Immediately extract and store leads from these URLs
                query_str = f"{trade} {state}"
                for url in urls:
                    if job.should_stop:
                        break
                    _extract_and_store(url, state, trade, query_str, job, seen_urls)

                # Brief pause between combos
                time.sleep(1)

            if job.should_stop:
                break

        job.phase = "done"

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        job.phase = "error"
        job.error = str(e)
    finally:
        job.running = False


def start_scrape(trades, states, results_per_query=10):
    """Launch a scrape job in a background thread."""
    global current_job

    if current_job.running:
        return False, "A scrape job is already running."

    current_job = ScrapeJob()
    thread = threading.Thread(
        target=_run_pipeline,
        args=(trades, states, results_per_query),
        daemon=True,
    )
    thread.start()
    return True, "Scrape started."


def stop_scrape():
    """Signal the current scrape to stop."""
    global current_job
    if current_job.running:
        current_job.stop()
        return True, "Stop signal sent."
    return False, "No scrape is running."


def get_scrape_status():
    """Get current scrape job status."""
    return current_job.status
