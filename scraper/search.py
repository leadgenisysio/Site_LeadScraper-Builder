"""Search module to find contractor websites using DuckDuckGo."""

import logging
import time
from urllib.parse import urlparse

from ddgs import DDGS

from config import EXCLUDED_DOMAINS, SEARCH_DELAY_SECONDS, STATES

logger = logging.getLogger(__name__)

# Major cities per target state — city-level queries surface actual contractor
# sites far better than state-level queries.
STATE_CITIES = {
    "NH": ["Manchester", "Nashua", "Concord", "Dover", "Rochester", "Keene", "Laconia"],
    "VT": ["Burlington", "South Burlington", "Rutland", "Montpelier", "Barre", "St Albans"],
    "CT": ["Bridgeport", "New Haven", "Hartford", "Stamford", "Waterbury", "Norwalk", "Danbury"],
    "MA": ["Boston", "Worcester", "Springfield", "Cambridge", "Lowell", "Brockton", "New Bedford"],
    "FL": ["Jacksonville", "Miami", "Tampa", "Orlando", "Fort Lauderdale", "St Petersburg", "Cape Coral"],
    "TX": ["Houston", "San Antonio", "Dallas", "Austin", "Fort Worth", "El Paso", "Arlington"],
}

# Maximum retries for a single search query when rate-limited
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds to wait before retrying after a failure


def _is_excluded(url):
    """Check if a URL belongs to an excluded domain."""
    try:
        domain = urlparse(url).netloc.lower()
        return any(excluded in domain for excluded in EXCLUDED_DOMAINS)
    except Exception:
        return True


def _ddg_search_with_retry(query, max_results):
    """Run a DuckDuckGo search with retry logic for rate limits."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ddgs = DDGS()
            results = list(ddgs.text(query, max_results=max_results))
            return results
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(
                kw in err_str for kw in ("ratelimit", "rate limit", "429", "too many")
            )
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                logger.warning(
                    f"Rate limited on attempt {attempt}/{MAX_RETRIES}, "
                    f"waiting {wait}s before retry..."
                )
                time.sleep(wait)
            else:
                logger.error(f"Search failed for '{query}' (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF)
                else:
                    return []
    return []


def search_contractors(trade, state_abbr, num_results=10):
    """
    Search DuckDuckGo for contractor websites matching a trade and state.

    Uses city-level queries for better results, cycling through major cities
    in the state until we have enough results.

    Returns a list of URLs that are likely individual contractor websites.
    """
    state_name = STATES.get(state_abbr, state_abbr)
    cities = STATE_CITIES.get(state_abbr, [state_name])

    all_urls = []
    seen = set()

    for city in cities:
        if len(all_urls) >= num_results:
            break

        query = f"{trade} {city} {state_abbr}"
        logger.info(f"Searching: {query}")

        raw_results = _ddg_search_with_retry(query, num_results + 10)

        for item in raw_results:
            url = item.get("href", "")
            if not url or url in seen:
                continue
            seen.add(url)

            if _is_excluded(url):
                logger.debug(f"  Excluded: {url}")
                continue

            all_urls.append(url)
            logger.info(f"  Found: {url}")

            if len(all_urls) >= num_results:
                break

        # Delay between queries to avoid rate limiting
        time.sleep(SEARCH_DELAY_SECONDS)

    return all_urls


def search_all(trades, state_abbrs, num_results=10, progress_callback=None):
    """
    Run searches for all trade+state combinations.

    Args:
        trades: List of trade names
        state_abbrs: List of state abbreviation strings
        num_results: Results per query
        progress_callback: Called with (current_step, total_steps, query_description)

    Returns:
        List of (url, state, trade, query) tuples
    """
    all_results = []
    total = len(trades) * len(state_abbrs)
    current = 0

    for state in state_abbrs:
        for trade in trades:
            current += 1
            desc = f"{trade} in {STATES.get(state, state)}"
            if progress_callback:
                progress_callback(current, total, desc)

            urls = search_contractors(trade, state, num_results)
            for url in urls:
                query_str = f"{trade} {state}"
                all_results.append((url, state, trade, query_str))

            # Extra delay between different trade/state combos
            time.sleep(1)

    return all_results
