"""Deploy demo sites to Cloudflare Pages via Wrangler CLI.

Cloudflare Pages is free with unlimited sites, bandwidth, and no credit system.
Uses the official Wrangler CLI for reliable deployments.
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile

from config import CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert a business name to a Cloudflare Pages project slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")[:40]
    short_hash = hashlib.md5(name.encode()).hexdigest()[:4]
    return f"demo-{slug}-{short_hash}"


def _run_wrangler(*args, env_extra=None):
    """Run a Wrangler CLI command and return (stdout, stderr, returncode)."""
    cmd = ["wrangler.cmd"] + list(args)
    env = os.environ.copy()
    env["CLOUDFLARE_API_TOKEN"] = CLOUDFLARE_API_TOKEN
    env["CLOUDFLARE_ACCOUNT_ID"] = CLOUDFLARE_ACCOUNT_ID
    if env_extra:
        env.update(env_extra)

    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        timeout=120,
        env=env,
        shell=True,
    )
    stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    return stdout, stderr, result.returncode


def is_configured() -> bool:
    """Return True if Cloudflare credentials are set."""
    return bool(CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID)


def deploy_demo_site(
    business_name: str,
    html_content: str,
    images: dict[str, bytes] | None = None,
) -> tuple[str, str]:
    """Deploy a demo site to Cloudflare Pages.

    Parameters
    ----------
    business_name:
        Human-readable business name used to derive the project slug.
    html_content:
        Complete HTML to serve as the site's ``index.html``.
    images:
        Optional mapping of ``{filename: image_bytes}``.
        Files are deployed under ``/img/``.

    Returns
    -------
    tuple[str, str]
        ``(project_name, site_url)`` where *site_url* is the public URL
        (e.g. ``https://demo-acme-roofing-a3f2.pages.dev``).
    """
    if not is_configured():
        raise ValueError("Cloudflare API token or Account ID not configured")

    project_name = _slugify(business_name)

    # Create a temp directory with the site files
    tmp_dir = tempfile.mkdtemp(prefix="cf-deploy-")
    try:
        # Write index.html
        with open(os.path.join(tmp_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

        # Write images
        if images:
            img_dir = os.path.join(tmp_dir, "img")
            os.makedirs(img_dir, exist_ok=True)
            for filename, img_bytes in images.items():
                with open(os.path.join(img_dir, filename), "wb") as f:
                    f.write(img_bytes)
            logger.info("Including %d image(s) in Cloudflare deploy", len(images))

        # Create the Pages project (ignore errors if it already exists)
        stdout, stderr, code = _run_wrangler(
            "pages", "project", "create", project_name,
            "--production-branch", "main",
        )
        if code != 0 and "already exists" not in stderr.lower() and "already exists" not in stdout.lower():
            # Try with a different name if taken
            alt_hash = hashlib.md5(f"{business_name}-retry".encode()).hexdigest()[:6]
            project_name = f"demo-{re.sub(r'-[a-f0-9]{4}$', '', project_name)}-{alt_hash}"
            stdout, stderr, code = _run_wrangler(
                "pages", "project", "create", project_name,
                "--production-branch", "main",
            )
            if code != 0 and "already exists" not in stderr.lower() and "already exists" not in stdout.lower():
                logger.error("Failed to create Cloudflare project: %s %s", stdout, stderr)
                raise RuntimeError(f"Failed to create Cloudflare project: {stderr}")

        logger.info("Cloudflare project ready: %s", project_name)

        # Deploy the files
        stdout, stderr, code = _run_wrangler(
            "pages", "deploy", tmp_dir,
            "--project-name", project_name,
            "--branch", "main",
        )
        if code != 0:
            logger.error("Cloudflare deploy failed: %s %s", stdout, stderr)
            raise RuntimeError(f"Cloudflare deploy failed: {stderr}")

        # Extract the URL from Wrangler output
        site_url = f"https://{project_name}.pages.dev"
        # Try to parse actual URL from output
        url_match = re.search(r"(https://[a-z0-9-]+\.pages\.dev)", stdout + stderr)
        if url_match:
            site_url = url_match.group(1)

        logger.info("Demo site live at %s", site_url)
        return project_name, site_url

    finally:
        # Clean up temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


def redeploy_site(
    project_name: str,
    html_content: str,
    images: dict[str, bytes] | None = None,
) -> None:
    """Redeploy updated files to an existing Cloudflare Pages project."""
    if not is_configured():
        raise ValueError("Cloudflare API token or Account ID not configured")

    tmp_dir = tempfile.mkdtemp(prefix="cf-redeploy-")
    try:
        with open(os.path.join(tmp_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

        if images:
            img_dir = os.path.join(tmp_dir, "img")
            os.makedirs(img_dir, exist_ok=True)
            for filename, img_bytes in images.items():
                with open(os.path.join(img_dir, filename), "wb") as f:
                    f.write(img_bytes)

        stdout, stderr, code = _run_wrangler(
            "pages", "deploy", tmp_dir,
            "--project-name", project_name,
            "--branch", "main",
        )
        if code != 0:
            logger.error("Cloudflare redeploy failed: %s %s", stdout, stderr)
            raise RuntimeError(f"Cloudflare redeploy failed: {stderr}")

        logger.info("Project %s redeployed", project_name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def delete_site(project_name: str) -> None:
    """Delete a Cloudflare Pages project."""
    if not is_configured():
        raise ValueError("Cloudflare API token or Account ID not configured")

    logger.info("Deleting Cloudflare project %s", project_name)
    stdout, stderr, code = _run_wrangler(
        "pages", "project", "delete", project_name, "--yes",
    )
    if code != 0:
        logger.error("Failed to delete project %s: %s %s", project_name, stdout, stderr)
        raise RuntimeError(f"Failed to delete Cloudflare project: {stderr}")

    logger.info("Project %s deleted", project_name)


def list_sites() -> list[dict]:
    """List all Cloudflare Pages projects.

    Returns a list of dicts with keys: name, url, created_on, etc.
    """
    if not is_configured():
        raise ValueError("Cloudflare API token or Account ID not configured")

    import requests

    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    resp = requests.get(
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/pages/projects",
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    sites = []
    for project in data.get("result", []):
        sites.append({
            "id": project.get("name", ""),  # CF uses project name as ID
            "name": project.get("name", ""),
            "url": f"https://{project.get('subdomain', project.get('name', '') + '.pages.dev')}",
            "custom_domain": None,
            "created_at": project.get("created_on", ""),
            "updated_at": project.get("latest_deployment", {}).get("created_on", ""),
            "screenshot_url": "",
        })

    logger.info("Listed %d Cloudflare Pages projects", len(sites))
    return sites
