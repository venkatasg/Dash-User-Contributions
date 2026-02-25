#!/usr/bin/env python3
"""
generate_docset.py
==================
Generates a Dash docset for HuggingFace Transformers documentation.

Downloads the latest rendered docs from huggingface.co and packages them
into a Dash-compatible .docset bundle with a SQLite search index.

Usage
-----
    python generate_docset.py [options]

Options
-------
    --version VERSION   Transformers version to package (default: latest from PyPI)
    --output-dir DIR    Where to write the .docset and .tgz (default: script directory)
    --workers N         Parallel download workers (default: 8)
    --no-archive        Skip creating the .tgz archive
    --skip-hf-css       Do not bundle the HuggingFace compiled CSS (pages rely on CDN)

Requirements
------------
    pip install requests beautifulsoup4 pyyaml lxml
"""

import argparse
import logging
import plistlib
import re
import shutil
import sqlite3
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urljoin

try:
    import requests
    import yaml
    from bs4 import BeautifulSoup
except ImportError as exc:
    sys.exit(
        f"Missing dependency: {exc}\n"
        "Install with: pip install requests beautifulsoup4 pyyaml lxml"
    )

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
DOCSET_NAME = "transformers"

TOCTREE_URL = (
    "https://raw.githubusercontent.com/huggingface/transformers"
    "/main/docs/source/en/_toctree.yml"
)
PYPI_URL = "https://pypi.org/pypi/transformers/json"
HF_DOCS_URL = "https://huggingface.co/docs/transformers/{version}/en/{page}"
HF_BASE = "https://huggingface.co"

# Seconds between successive requests *per worker* to avoid hammering the server
REQUEST_DELAY = 0.15

# HTTP headers that mimic a real browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Version discovery ──────────────────────────────────────────────────────────

def get_latest_version() -> str:
    """Return the latest published transformers version from PyPI."""
    try:
        resp = requests.get(PYPI_URL, timeout=10, headers=_HEADERS)
        resp.raise_for_status()
        version = resp.json()["info"]["version"]
        log.info("Latest version from PyPI: %s", version)
        return version
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not fetch version from PyPI (%s). Using 4.47.0.", exc)
        return "4.47.0"


# ── Navigation ─────────────────────────────────────────────────────────────────

def fetch_toctree(version: str) -> list:
    """Fetch _toctree.yml; fall back to main branch if versioned tag not available."""
    # Try the tag for the exact version first
    tag_url = (
        f"https://raw.githubusercontent.com/huggingface/transformers"
        f"/v{version}/docs/source/en/_toctree.yml"
    )
    for url in (tag_url, TOCTREE_URL):
        try:
            resp = requests.get(url, timeout=30, headers=_HEADERS)
            if resp.status_code == 200:
                log.info("Fetched toctree from: %s", url)
                return yaml.safe_load(resp.text)
        except Exception as exc:  # noqa: BLE001
            log.debug("Toctree fetch failed for %s: %s", url, exc)
    raise RuntimeError("Could not fetch _toctree.yml from GitHub")


def collect_pages(toctree: list) -> list[tuple[str, str]]:
    """
    Recursively walk the toctree and collect (title, slug) pairs.
    Slugs may contain a single slash (e.g. "model_doc/bert").
    """
    pages: list[tuple[str, str]] = []

    def walk(nodes: list) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if "local" in node:
                title = node.get("title", node["local"])
                pages.append((title, node["local"]))
            if "sections" in node:
                walk(node["sections"])

    walk(toctree)
    return pages


# ── CSS bundling ───────────────────────────────────────────────────────────────

def find_hf_css_url(html: str) -> str | None:
    """Extract the URL of HuggingFace's compiled Tailwind CSS from a page."""
    match = re.search(r'href="(/front/build/[^"]+/style\.css)"', html)
    if match:
        return urljoin(HF_BASE, match.group(1))
    return None


def download_hf_css(url: str, session: requests.Session, dest: Path) -> bool:
    """Download the HuggingFace compiled CSS and save to *dest*. Returns success."""
    try:
        resp = session.get(url, timeout=60, headers=_HEADERS)
        resp.raise_for_status()
        dest.write_text(resp.text, encoding="utf-8")
        log.info(
            "Downloaded HF CSS → %s (%.0f KB)",
            dest.name,
            dest.stat().st_size / 1024,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to download HF CSS: %s", exc)
        return False


# ── Entry classification ───────────────────────────────────────────────────────

def classify_api_entry(span_id: str, heading_text: str) -> tuple[str, str]:
    """
    Map a ``<span id="transformers.*">`` to a (display_name, dash_type) pair.

    Heuristic
    ---------
    - ``transformers.Name``              → Class or Function (depends on heading)
    - ``transformers.ClassName.method``  → Method
    - ``transformers.Name.attr.sub``     → Attribute
    """
    # Strip "transformers." prefix
    name = span_id[len("transformers."):]
    parts = name.split(".")

    if len(parts) == 1:
        # Top-level entry
        if re.match(r"^class\s+", heading_text):
            return parts[0], "Class"
        return parts[0], "Function"

    if len(parts) == 2:
        # ClassName.method_name
        return name, "Method"

    # Deeper nesting (e.g. ClassName.attr.sub) → Attribute
    return name, "Attribute"


# ── HTML processing ────────────────────────────────────────────────────────────

def make_relative_css_path(slug: str, filename: str) -> str:
    """Return the correct relative path from a page slug to a CSS file in Documents/."""
    depth = slug.count("/")
    prefix = "../" * depth
    return f"{prefix}{filename}"


def process_page(
    html: str,
    slug: str,
    version: str,
    hf_css_filename: str | None,
) -> tuple[str, list[tuple[str, str, str]]]:
    """
    Post-process a downloaded HTML page for use inside a Dash docset.

    Actions performed
    -----------------
    1. Remove ``<script>`` tags (SvelteKit client-side JS not needed).
    2. Rewrite the HuggingFace compiled CSS ``<link>`` to point at the local copy
       bundled inside the docset (if *hf_css_filename* is set).
    3. Inject ``<link rel="stylesheet" href="hidesidebar.css">`` to hide navigation.
    4. Make relative ``<img src>`` and ``<a href>`` URLs absolute so that images
       and cross-links work when the page is loaded from inside the .docset.
    5. Insert ``<a name="//apple_ref/…" class="dashAnchor">`` anchors before each
       ``<span id="transformers.*">`` API entry so Dash can index them.

    Returns
    -------
    (processed_html, entries)
        Where *entries* is a list of (name, type, path) tuples for the SQLite index.
    """
    soup = BeautifulSoup(html, "lxml")
    entries: list[tuple[str, str, str]] = []

    # ── 1. Remove client-side scripts ─────────────────────────────────────────
    for script in soup.find_all("script"):
        script.decompose()

    # ── 2. Rewrite HuggingFace compiled CSS href ───────────────────────────────
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href", "")
        if "/front/build/" in href and "style.css" in href:
            if hf_css_filename:
                link["href"] = make_relative_css_path(slug, hf_css_filename)
            else:
                # Make absolute so it can still load from the CDN
                if href.startswith("/"):
                    link["href"] = urljoin(HF_BASE, href)

    # ── 3. Inject hidesidebar.css ──────────────────────────────────────────────
    head = soup.find("head") or soup.new_tag("head")
    hide_link = soup.new_tag(
        "link",
        rel="stylesheet",
        href=make_relative_css_path(slug, "hidesidebar.css"),
    )
    head.append(hide_link)

    # ── 4. Make relative URLs absolute ────────────────────────────────────────
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if src.startswith("/"):
            img["src"] = urljoin(HF_BASE, src)

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith("/") and not href.startswith("//"):
            a_tag["href"] = urljoin(HF_BASE, href)

    # ── 5. Inject Dash anchors and collect index entries ──────────────────────
    api_spans = soup.find_all(
        "span", id=lambda x: x and x.startswith("transformers.")
    )
    for span in api_spans:
        span_id: str = span["id"]
        heading = span.find(["h3", "h4", "h5"])
        heading_text = heading.get_text().strip() if heading else ""

        display_name, entry_type = classify_api_entry(span_id, heading_text)

        # Insert Dash TOC anchor as the first child of the span
        anchor = soup.new_tag(
            "a",
            attrs={
                "name": f"//apple_ref/cpp/{entry_type}/{quote(display_name)}",
                "class": "dashAnchor",
            },
        )
        span.insert(0, anchor)

        entries.append((display_name, entry_type, f"{slug}.html#{span_id}"))

    # ── Collect section-level headings as Section entries ─────────────────────
    for a_tag in soup.find_all("a", class_="header-link"):
        href = a_tag.get("href", "")
        if not (href.startswith("#") and len(href) > 1):
            continue
        section_id = href[1:]
        if section_id.startswith("transformers."):
            # Already captured as an API entry above
            continue
        parent = a_tag.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"])
        if parent:
            section_name = parent.get_text().strip()
            # Trim the anchor link icon text that's sometimes included
            section_name = re.sub(r"\s*\ue0a0.*$", "", section_name).strip()
            if section_name:
                entries.append((section_name, "Section", f"{slug}.html{href}"))

    # ── Add a Guide entry for the page itself ─────────────────────────────────
    title_tag = soup.find("title")
    if title_tag:
        page_title = title_tag.get_text().strip().split(" - ")[0].strip()
        if page_title:
            entries.append((page_title, "Guide", f"{slug}.html"))

    return str(soup), entries


# ── Downloading ────────────────────────────────────────────────────────────────

def download_page(
    url: str,
    session: requests.Session,
    max_retries: int = 3,
) -> str | None:
    """Download *url* and return the HTML body, or ``None`` on permanent failure."""
    for attempt in range(max_retries):
        try:
            resp = session.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 404:
                log.warning("404 Not Found: %s", url)
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            wait = 2 ** attempt
            log.warning(
                "Attempt %d/%d failed for %s: %s — retrying in %ds",
                attempt + 1, max_retries, url, exc, wait,
            )
            if attempt < max_retries - 1:
                time.sleep(wait)
    log.error("Giving up on %s after %d attempts", url, max_retries)
    return None


# ── Docset scaffolding ─────────────────────────────────────────────────────────

def create_docset_dirs(docset_dir: Path) -> tuple[Path, Path, Path]:
    """Create ``Contents/``, ``Resources/``, ``Documents/`` and return all three."""
    contents = docset_dir / "Contents"
    resources = contents / "Resources"
    documents = resources / "Documents"
    documents.mkdir(parents=True, exist_ok=True)
    return contents, resources, documents


def write_info_plist(contents_dir: Path, version: str) -> None:
    """Write the ``Info.plist`` required by Dash."""
    plist: dict = {
        "CFBundleIdentifier": DOCSET_NAME,
        "CFBundleName": "Transformers",
        "DocSetPlatformFamily": DOCSET_NAME,
        "isDashDocset": True,
        "isJavaScriptEnabled": False,
        "dashIndexFilePath": "index.html",
        "DashDocSetFamily": "dashtoc",
        "DashDocSetFallbackURL": (
            f"https://huggingface.co/docs/transformers/v{version}/en/"
        ),
        "DashDocSetKeyword": DOCSET_NAME,
        "DashDocSetPluginKeyword": DOCSET_NAME,
        "DashWebSearchKeyword": DOCSET_NAME,
    }
    plist_path = contents_dir / "Info.plist"
    with open(plist_path, "wb") as fh:
        plistlib.dump(plist, fh)
    log.debug("Wrote %s", plist_path)


def init_database(db_path: Path) -> sqlite3.Connection:
    """Create the Dash SQLite search index at *db_path*."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE IF EXISTS searchIndex")
    conn.execute(
        """
        CREATE TABLE searchIndex (
            id   INTEGER PRIMARY KEY,
            name TEXT,
            type TEXT,
            path TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path)")
    conn.commit()
    return conn


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Dash docset for HuggingFace Transformers docs",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        metavar="VERSION",
        help="Transformers version to package (e.g. 4.47.0). Defaults to latest on PyPI.",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=str(SCRIPT_DIR),
        help="Directory where the .docset folder and .tgz archive are written.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="Number of parallel download workers.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip building the .tgz archive (useful for quick iteration).",
    )
    parser.add_argument(
        "--skip-hf-css",
        action="store_true",
        help=(
            "Do not download and bundle the HuggingFace compiled CSS. "
            "Pages will load it from the CDN instead (requires internet in Dash)."
        ),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    version = args.version or get_latest_version()

    log.info("=" * 60)
    log.info("Building Transformers %s docset", version)
    log.info("Output directory: %s", output_dir)
    log.info("=" * 60)

    # ── Create docset directory structure ──────────────────────────────────────
    docset_dir = output_dir / f"{DOCSET_NAME}.docset"
    if docset_dir.exists():
        log.info("Removing existing docset directory: %s", docset_dir)
        shutil.rmtree(docset_dir)

    contents_dir, resources_dir, documents_dir = create_docset_dirs(docset_dir)

    # ── Info.plist ─────────────────────────────────────────────────────────────
    write_info_plist(contents_dir, version)

    # ── SQLite index ───────────────────────────────────────────────────────────
    db_path = resources_dir / "docSet.dsidx"
    conn = init_database(db_path)

    # ── Icons ──────────────────────────────────────────────────────────────────
    for icon_name in ("icon.png", "icon@2x.png"):
        src = SCRIPT_DIR / icon_name
        if src.exists():
            shutil.copy2(src, docset_dir / icon_name)
            log.info("Copied icon: %s", icon_name)
        else:
            log.warning("Icon not found: %s", src)

    # ── hidesidebar.css ────────────────────────────────────────────────────────
    css_src = SCRIPT_DIR / "hidesidebar.css"
    if not css_src.exists():
        log.warning("hidesidebar.css not found at %s", css_src)
    else:
        shutil.copy2(css_src, documents_dir / "hidesidebar.css")
        log.info("Copied hidesidebar.css into Documents/")

    # ── Navigation ─────────────────────────────────────────────────────────────
    log.info("Fetching _toctree.yml …")
    toctree = fetch_toctree(version)
    pages = collect_pages(toctree)
    log.info("Navigation contains %d pages", len(pages))

    # ── Optionally download HuggingFace compiled CSS ───────────────────────────
    hf_css_filename: str | None = None
    session = requests.Session()

    if not args.skip_hf_css:
        log.info("Downloading HuggingFace compiled CSS …")
        # Download the index page to find the CSS URL
        index_url = HF_DOCS_URL.format(version=f"v{version}", page="index")
        index_html = download_page(index_url, session)
        if index_html:
            hf_css_url = find_hf_css_url(index_html)
            if hf_css_url:
                hf_css_filename = "hf_style.css"
                css_dest = documents_dir / hf_css_filename
                if not download_hf_css(hf_css_url, session, css_dest):
                    log.warning("Falling back: pages will load HF CSS from CDN.")
                    hf_css_filename = None
            else:
                log.warning("Could not locate HF CSS URL in index page.")
        else:
            log.warning("Could not download index page to find HF CSS URL.")

    # ── Download and process all pages ────────────────────────────────────────
    success_count = 0
    error_count = 0
    total_entries = 0

    def process_one(
        title_slug: tuple[str, str],
    ) -> tuple[str, str, list[tuple[str, str, str]]] | None:
        """Worker: download + process one page. Returns (slug, html, entries) or None."""
        _title, slug = title_slug
        url = HF_DOCS_URL.format(version=f"v{version}", page=slug)
        time.sleep(REQUEST_DELAY)  # polite rate-limiting
        html = download_page(url, session)
        if html is None:
            return None
        processed_html, page_entries = process_page(html, slug, version, hf_css_filename)
        return slug, processed_html, page_entries

    log.info("Downloading %d pages with %d workers …", len(pages), args.workers)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(process_one, page): page for page in pages}

        for future in as_completed(future_map):
            page_info = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                log.error("Unhandled error for %s: %s", page_info[1], exc)
                error_count += 1
                continue

            if result is None:
                error_count += 1
                continue

            slug, processed_html, page_entries = result

            # Save HTML file (create subdirectories as needed)
            out_file = documents_dir / f"{slug}.html"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(processed_html, encoding="utf-8")

            # Index entries into SQLite
            for name, entry_type, path in page_entries:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO searchIndex(name, type, path)"
                        " VALUES (?, ?, ?)",
                        (name, entry_type, path),
                    )
                except sqlite3.Error as db_exc:
                    log.debug("DB insert skipped for %r: %s", name, db_exc)

            total_entries += len(page_entries)
            success_count += 1
            log.info(
                "[%d/%d] ✓ %s  (%d entries)",
                success_count,
                len(pages),
                slug,
                len(page_entries),
            )

    conn.commit()
    conn.close()

    log.info(
        "Finished: %d pages OK, %d errors, %d index entries",
        success_count,
        error_count,
        total_entries,
    )

    # ── Archive ────────────────────────────────────────────────────────────────
    if not args.no_archive:
        archive_path = output_dir / f"{DOCSET_NAME}.tgz"
        log.info("Creating archive: %s", archive_path)
        with tarfile.open(str(archive_path), "w:gz") as tar:
            tar.add(str(docset_dir), arcname=docset_dir.name)
        size_mb = archive_path.stat().st_size / 1_000_000
        log.info("Archive created: %s (%.1f MB)", archive_path, size_mb)

    log.info("=" * 60)
    log.info("Docset: %s", docset_dir)
    log.info("Version: %s", version)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
