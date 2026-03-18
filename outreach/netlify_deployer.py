"""Deploy demo sites to Netlify via their REST API.

Uses the file-digest deploy method (same approach as the Netlify CLI) for
reliable Content-Type detection.  Each deploy uploads ``index.html`` and a
``_headers`` file that forces ``text/html`` serving.
"""

import hashlib
import logging
import re

import requests

from config import NETLIFY_API_BASE, NETLIFY_API_TOKEN

logger = logging.getLogger(__name__)

# Netlify _headers file — ensures correct Content-Type for all file types
_HEADERS_CONTENT = """\
/index.html
  Content-Type: text/html; charset=utf-8
/img/*.jpg
  Content-Type: image/jpeg
  Cache-Control: public, max-age=31536000, immutable
/img/*.jpeg
  Content-Type: image/jpeg
  Cache-Control: public, max-age=31536000, immutable
/img/*.png
  Content-Type: image/png
  Cache-Control: public, max-age=31536000, immutable
/img/*.webp
  Content-Type: image/webp
  Cache-Control: public, max-age=31536000, immutable
/img/*.svg
  Content-Type: image/svg+xml
  Cache-Control: public, max-age=31536000, immutable
/*
  X-Content-Type-Options: nosniff
"""


def _slugify(name: str) -> str:
    """Convert a business name to a URL-safe slug.

    Lowercase the name, replace non-alphanumeric characters with hyphens,
    strip leading/trailing hyphens, and truncate to 30 characters.  A short
    hash (first 4 hex chars of the MD5 of the original name) is appended for
    uniqueness, and the whole thing is prefixed with ``demo-``.

    Example::

        >>> _slugify("Acme Roofing LLC")
        'demo-acme-roofing-llc-a3f2'
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = slug[:30]
    short_hash = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"demo-{slug}-{short_hash}"


def _sha1(data: bytes) -> str:
    """Return the hex SHA-1 digest of *data*."""
    return hashlib.sha1(data).hexdigest()


def _deploy_files(site_id: str, files: dict[str, bytes]) -> str:
    """Deploy files to a Netlify site using the file-digest API.

    Parameters
    ----------
    site_id:
        Netlify site ID to deploy to.
    files:
        Mapping of ``{path: content_bytes}``  e.g.
        ``{"/index.html": b"<html>..."}``

    Returns
    -------
    str
        The deploy ID.
    """
    auth = {"Authorization": f"Bearer {NETLIFY_API_TOKEN}"}

    # Build the file manifest  {path: sha1}
    manifest = {path: _sha1(data) for path, data in files.items()}

    # Step 1: Create the deploy with the manifest
    logger.info("Creating deploy for site %s with %d file(s)", site_id, len(files))
    resp = requests.post(
        f"{NETLIFY_API_BASE}/sites/{site_id}/deploys",
        headers={**auth, "Content-Type": "application/json"},
        json={"files": manifest},
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Failed to create deploy: %s %s", resp.status_code, resp.text
        )
        raise

    deploy_data = resp.json()
    deploy_id = deploy_data["id"]
    required_hashes = set(deploy_data.get("required", []))
    logger.info(
        "Deploy %s created; %d file(s) need uploading",
        deploy_id,
        len(required_hashes),
    )

    # Step 2: Upload each required file
    for path, data in files.items():
        file_hash = _sha1(data)
        if file_hash not in required_hashes:
            logger.debug("File %s already cached on Netlify, skipping", path)
            continue

        # Strip leading slash for the PUT path
        upload_path = path.lstrip("/")
        logger.info("Uploading %s (%d bytes)", upload_path, len(data))
        resp = requests.put(
            f"{NETLIFY_API_BASE}/deploys/{deploy_id}/files/{upload_path}",
            headers={**auth, "Content-Type": "application/octet-stream"},
            data=data,
            timeout=60,
        )

        try:
            resp.raise_for_status()
        except requests.HTTPError:
            logger.error(
                "Failed to upload %s: %s %s",
                upload_path,
                resp.status_code,
                resp.text,
            )
            raise

    logger.info("Deploy %s complete", deploy_id)
    return deploy_id


def deploy_demo_site(
    business_name: str,
    html_content: str,
    images: dict[str, bytes] | None = None,
) -> tuple[str, str]:
    """Deploy a demo site (HTML + optional images) to Netlify.

    Parameters
    ----------
    business_name:
        Human-readable business name used to derive the subdomain slug.
    html_content:
        Complete HTML to serve as the site's ``index.html``.
    images:
        Optional mapping of ``{filename: image_bytes}``, e.g.
        ``{"hero.jpg": b"\\xff\\xd8..."}``  Files are deployed under ``/img/``.

    Returns
    -------
    tuple[str, str]
        ``(site_id, site_url)`` where *site_url* is the public Netlify URL
        (e.g. ``https://demo-acme-roofing-llc-a3f2.netlify.app``).

    Raises
    ------
    ValueError
        If ``NETLIFY_API_TOKEN`` is not configured.
    requests.HTTPError
        If any Netlify API call fails.
    """
    if not NETLIFY_API_TOKEN:
        raise ValueError("Netlify API token not configured")

    slug = _slugify(business_name)
    headers = {
        "Authorization": f"Bearer {NETLIFY_API_TOKEN}",
        "Content-Type": "application/json",
    }

    # --- 1. Create the site ---------------------------------------------------
    logger.info("Creating Netlify site with slug '%s'", slug)
    resp = requests.post(
        f"{NETLIFY_API_BASE}/sites",
        headers=headers,
        json={"name": slug},
        timeout=30,
    )

    # If the name is already taken (422), retry with a different hash suffix.
    if resp.status_code == 422:
        alt_hash = hashlib.md5(
            f"{business_name}-retry".encode()
        ).hexdigest()[:6]
        slug = f"demo-{re.sub(r'-[a-f0-9]{4}$', '', slug)}-{alt_hash}"
        logger.warning("Slug collision; retrying with '%s'", slug)
        resp = requests.post(
            f"{NETLIFY_API_BASE}/sites",
            headers=headers,
            json={"name": slug},
            timeout=30,
        )

    try:
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Failed to create Netlify site: %s %s", resp.status_code, resp.text
        )
        raise

    site_id: str = resp.json()["id"]
    logger.info("Netlify site created: site_id=%s", site_id)

    # --- 2. Deploy HTML + images via file-digest API ─────────────────────────
    files = {
        "/index.html": html_content.encode("utf-8"),
        "/_headers": _HEADERS_CONTENT.encode("utf-8"),
    }

    # Add images under /img/
    if images:
        for filename, img_bytes in images.items():
            files[f"/img/{filename}"] = img_bytes
        logger.info("Including %d image(s) in deploy", len(images))

    _deploy_files(site_id, files)

    site_url = f"https://{slug}.netlify.app"
    logger.info("Demo site live at %s", site_url)
    return site_id, site_url


def redeploy_site(
    site_id: str,
    html_content: str,
    images: dict[str, bytes] | None = None,
) -> None:
    """Redeploy updated HTML + images to an existing Netlify site.

    Useful for fixing an existing demo without creating a new site.
    """
    if not NETLIFY_API_TOKEN:
        raise ValueError("Netlify API token not configured")

    files = {
        "/index.html": html_content.encode("utf-8"),
        "/_headers": _HEADERS_CONTENT.encode("utf-8"),
    }

    if images:
        for filename, img_bytes in images.items():
            files[f"/img/{filename}"] = img_bytes
        logger.info("Including %d image(s) in redeploy", len(images))

    _deploy_files(site_id, files)
    logger.info("Site %s redeployed", site_id)


def delete_netlify_site(site_id: str) -> None:
    """Delete a Netlify site to clean up rejected demos.

    Parameters
    ----------
    site_id:
        The Netlify site ID to remove.

    Raises
    ------
    ValueError
        If ``NETLIFY_API_TOKEN`` is not configured.
    requests.HTTPError
        If the DELETE request fails.
    """
    if not NETLIFY_API_TOKEN:
        raise ValueError("Netlify API token not configured")

    headers = {"Authorization": f"Bearer {NETLIFY_API_TOKEN}"}
    logger.info("Deleting Netlify site %s", site_id)
    resp = requests.delete(
        f"{NETLIFY_API_BASE}/sites/{site_id}",
        headers=headers,
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Failed to delete Netlify site %s: %s %s",
            site_id,
            resp.status_code,
            resp.text,
        )
        raise

    logger.info("Netlify site %s deleted", site_id)


def list_netlify_sites() -> list[dict]:
    """Return all Netlify sites owned by the configured account.

    Each dict has keys: ``id``, ``name``, ``url``, ``created_at``,
    ``updated_at``, ``screenshot_url``.

    Raises
    ------
    ValueError
        If ``NETLIFY_API_TOKEN`` is not configured.
    """
    if not NETLIFY_API_TOKEN:
        raise ValueError("Netlify API token not configured")

    headers = {"Authorization": f"Bearer {NETLIFY_API_TOKEN}"}
    sites: list[dict] = []
    page = 1

    while True:
        resp = requests.get(
            f"{NETLIFY_API_BASE}/sites",
            headers=headers,
            params={"page": page, "per_page": 100},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for s in batch:
            sites.append({
                "id": s["id"],
                "name": s.get("name", ""),
                "url": s.get("ssl_url") or s.get("url", ""),
                "custom_domain": s.get("custom_domain"),
                "created_at": s.get("created_at", ""),
                "updated_at": s.get("updated_at", ""),
                "screenshot_url": s.get("screenshot_url", ""),
            })
        # Netlify returns fewer items than per_page when on last page
        if len(batch) < 100:
            break
        page += 1

    logger.info("Listed %d Netlify sites", len(sites))
    return sites
