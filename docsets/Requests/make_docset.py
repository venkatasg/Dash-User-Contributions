#!/usr/bin/env python3
"""
Generate the Requests Dash docset from requests.readthedocs.io.

Dependencies (install with pip):
    requests
    beautifulsoup4

Usage:
    python make_docset.py [--icon-dir DIR]

    --icon-dir DIR   Directory containing icon.png (16x16) and
                     icon@2x.png (32x32). Defaults to the directory
                     containing this script.

The script produces Requests.tgz in the current working directory.
It hides the left navigation sidebar and inline table-of-contents
sections so pages render cleanly inside the Dash app.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import tarfile
import time
import urllib.parse
from pathlib import Path

import requests as http  # aliased to avoid clash with the library being documented
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://requests.readthedocs.io/en/latest/"
DOCSET_NAME = "Requests"
DOCSET_DIR = Path(f"{DOCSET_NAME}.docset")
DOCS_DIR = DOCSET_DIR / "Contents" / "Resources" / "Documents"
DB_PATH = DOCSET_DIR / "Contents" / "Resources" / "docSet.dsidx"
INFO_PLIST_PATH = DOCSET_DIR / "Contents" / "Info.plist"

# Polite delay between HTTP requests (seconds)
REQUEST_DELAY = 0.15

# ---------------------------------------------------------------------------
# CSS injected into every HTML page to hide navigation in Dash
# ---------------------------------------------------------------------------

DASH_CSS = """\
/* ── Dash docset: hide left sidebar and table of contents ── */

/* Alabaster theme sidebar */
.sphinxsidebar,
.sphinxsidebarwrapper {
    display: none !important;
}

/* ReadTheDocs version selector and injected widgets */
.rst-versions,
#rtd-search-form,
.ethical-rtd,
.injected {
    display: none !important;
}

/* Inline table-of-contents blocks (toctree and "Contents" topic) */
.toctree-wrapper,
div.topic.contents,
nav.contents {
    display: none !important;
}

/* Expand the main content to fill the full page width */
.documentwrapper {
    float: none !important;
    width: 100% !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
}

.document {
    max-width: none !important;
}

.bodywrapper {
    margin-left: 0 !important;
    margin-right: 0 !important;
}
"""

# ---------------------------------------------------------------------------
# Info.plist
# ---------------------------------------------------------------------------

INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>requests</string>
    <key>CFBundleName</key>
    <string>Requests</string>
    <key>DocSetPlatformFamily</key>
    <string>requests</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>index.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
</dict>
</plist>
"""

# Sphinx dl class → Dash entry type
_DL_TYPE_MAP: dict[str, str] = {
    "py function": "Function",
    "py class": "Class",
    "py method": "Method",
    "py attribute": "Attribute",
    "py exception": "Exception",
    "py data": "Constant",
    "py property": "Property",
    "py staticmethod": "Method",
    "py classmethod": "Method",
}

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def make_session() -> http.Session:
    session = http.Session()
    session.headers["User-Agent"] = (
        "requests-docset-generator/1.0 "
        "(+https://github.com/Kapeli/Dash-User-Contributions)"
    )
    return session


def strip_query(url: str) -> str:
    """Remove query string and fragment from *url*."""
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))


def url_to_local(url: str) -> Path:
    """
    Convert an absolute URL to a relative path inside DOCS_DIR.

    The BASE_URL prefix is stripped, query strings and fragments are
    ignored, and bare directory paths get ``index.html`` appended.
    """
    path = urllib.parse.urlparse(url).path
    # Strip the base prefix so files live at the top of DOCS_DIR
    base_path = urllib.parse.urlparse(BASE_URL).path  # e.g. /en/latest/
    if path.startswith(base_path):
        path = path[len(base_path):]
    path = path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    return Path(path)


def resolve(href: str, page_url: str) -> str | None:
    """
    Resolve *href* (possibly relative) against *page_url*.

    Returns the canonical absolute URL (no query string or fragment),
    or ``None`` if the link is external, anchor-only, or non-HTTP.
    """
    if not href or href.startswith(("data:", "mailto:", "javascript:", "#")):
        return None
    if href.startswith("//"):
        href = "https:" + href
    full = urllib.parse.urljoin(page_url, href)
    if not full.startswith(BASE_URL):
        return None
    return strip_query(full)


# ---------------------------------------------------------------------------
# Docset scaffolding
# ---------------------------------------------------------------------------


def setup_docset() -> None:
    """Create (or recreate) the empty docset directory tree."""
    if DOCSET_DIR.exists():
        shutil.rmtree(DOCSET_DIR)
    DOCS_DIR.mkdir(parents=True)
    INFO_PLIST_PATH.write_text(INFO_PLIST, encoding="utf-8")
    print("Created docset skeleton.")


def create_db() -> sqlite3.Connection:
    """Create and return an open connection to the Dash search index."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE searchIndex(
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


# ---------------------------------------------------------------------------
# HTML processing
# ---------------------------------------------------------------------------


def process_html(content: str, page_url: str) -> str:
    """
    Parse *content* (HTML text for *page_url*) and:

    1. Inject DASH_CSS into ``<head>`` to hide the sidebar and TOC.
    2. Strip query strings from local asset ``href``/``src`` attributes
       so they match the filenames saved on disk.
    """
    soup = BeautifulSoup(content, "html.parser")

    # 1. Inject CSS
    head = soup.find("head")
    if head:
        style = soup.new_tag("style")
        style.string = DASH_CSS
        head.append(style)

    # 2. Strip query strings from local asset references
    for tag in soup.find_all(True):
        for attr in ("href", "src"):
            val = tag.get(attr, "")
            if val and "?" in val and not val.startswith(("http", "//", "data:")):
                tag[attr] = val.split("?")[0]

    return str(soup)


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------


def download(
    session: http.Session,
    url: str,
    local: Path,
    *,
    is_html: bool = True,
) -> bool:
    """
    Fetch *url* and save to *local*.

    HTML pages pass through :func:`process_html` first; binary files are
    saved verbatim.  Already-existing files are skipped.

    Returns ``True`` on success.
    """
    if local.exists():
        return True

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except http.RequestException as exc:
        print(f"    SKIP {url}  ({exc})")
        return False

    local.parent.mkdir(parents=True, exist_ok=True)
    ctype = resp.headers.get("content-type", "")
    if is_html and ("text/html" in ctype or local.suffix == ".html"):
        local.write_text(process_html(resp.text, url), encoding="utf-8")
    else:
        local.write_bytes(resp.content)
    return True


def collect_pages(session: http.Session) -> dict[str, Path]:
    """
    Crawl the Requests docs site and return every HTML page found.

    Starts from a set of known seed URLs and follows every internal
    link.  Returns ``{absolute_url: local_path}``.
    """
    queue: set[str] = set()
    seen: set[str] = set()
    pages: dict[str, Path] = {}

    def enqueue(url: str) -> None:
        url = strip_query(url)
        if url.startswith(BASE_URL) and url not in seen and url not in queue:
            queue.add(url)

    # Seed pages – cover all major sections directly in case a page is
    # not reachable via links from another seed.
    for rel in (
        "",
        "api/",
        "user/install/",
        "user/quickstart/",
        "user/advanced/",
        "user/authentication/",
        "community/faq/",
        "community/recommended/",
        "community/vulnerabilities/",
        "dev/contributing/",
        "dev/authors/",
    ):
        enqueue(BASE_URL + rel)

    while queue:
        url = queue.pop()
        seen.add(url)
        local = DOCS_DIR / url_to_local(url)
        pages[url] = local

        # Only follow links from HTML pages
        if not (url.endswith(".html") or url.endswith("/")):
            continue

        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except http.RequestException:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            child = resolve(a["href"], url)
            if child:
                enqueue(child)

        time.sleep(REQUEST_DELAY)

    return pages


def collect_assets(pages: dict[str, Path]) -> dict[str, Path]:
    """
    Scan saved HTML files for CSS / JS / image references that belong
    to the docs site.  Returns ``{absolute_url: local_path}``.
    """
    assets: dict[str, Path] = {}

    for url, local in pages.items():
        if not local.exists() or local.suffix != ".html":
            continue
        try:
            soup = BeautifulSoup(local.read_text(encoding="utf-8"), "html.parser")
        except Exception:
            continue

        for tag in soup.find_all(["link", "script", "img"]):
            attr = "href" if tag.name == "link" else "src"
            val = tag.get(attr, "")
            full = resolve(val, url)
            if full and full not in assets and full not in pages:
                assets[full] = DOCS_DIR / url_to_local(full)

    return assets


# ---------------------------------------------------------------------------
# Index (Dash SQLite database)
# ---------------------------------------------------------------------------


def _dl_type(dl_tag) -> str:
    """Map a Sphinx ``<dl>`` element's class list to a Dash entry type."""
    classes = " ".join(dl_tag.get("class", []))
    for key, dash_type in _DL_TYPE_MAP.items():
        if key in classes:
            return dash_type
    return "Function"


def index_entries(conn: sqlite3.Connection, session: http.Session) -> None:
    """
    Fetch the API reference page, locate every Sphinx ``<dl class="py …">``
    block, and insert each documented symbol into the Dash search index.

    The name is read from the ``id`` attribute on the ``<dt>`` element
    (e.g. ``requests.Session.get``).  The type comes directly from the
    ``<dl>`` class attribute, which Sphinx sets to ``py function``,
    ``py class``, ``py method``, etc.
    """
    print("Indexing API entries…")
    api_url = BASE_URL + "api/"
    try:
        resp = session.get(api_url, timeout=30)
        resp.raise_for_status()
    except http.RequestException as exc:
        print(f"  Could not fetch {api_url}: {exc}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    cur = conn.cursor()
    count = 0

    # Every Sphinx-documented Python object lives in a <dl class="py …"> block.
    # The <dt> child carries the id="requests.Something" anchor.
    for dl in soup.find_all("dl", class_=lambda c: c and "py" in c):
        dt = dl.find("dt", id=True)
        if dt is None:
            continue

        symbol_id: str = dt["id"]
        if not symbol_id.startswith("requests."):
            continue

        entry_type = _dl_type(dl)
        # Path relative to DOCS_DIR: "api/#requests.Session.get"
        path = f"api/#{symbol_id}"

        try:
            cur.execute(
                "INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?, ?, ?)",
                (symbol_id, entry_type, path),
            )
            count += 1
        except sqlite3.Error:
            pass

    conn.commit()
    print(f"  Indexed {count} entries.")


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------


def detect_version(session: http.Session) -> str:
    """
    Try to read the library version from the docs page title
    (e.g. "Requests 2.32.3 documentation").  Falls back to "latest".
    """
    try:
        resp = session.get(BASE_URL, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.find("title")
        if title:
            import re
            m = re.search(r"(\d+\.\d+[\.\d]*)", title.get_text())
            if m:
                return m.group(1)
    except Exception:
        pass
    return "latest"


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------


def package(icon_dir: Path | None = None) -> None:
    """Copy icons into the docset (if found) and create ``Requests.tgz``."""
    if icon_dir:
        for name in ("icon.png", "icon@2x.png"):
            src = icon_dir / name
            if src.exists():
                shutil.copy2(src, DOCSET_DIR / name)
                print(f"  Copied {name}")

    archive = f"{DOCSET_NAME}.tgz"
    print(f"Creating {archive}…")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(str(DOCSET_DIR), arcname=str(DOCSET_DIR))
    print(f"Done → {archive}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the Requests Dash docset from requests.readthedocs.io"
    )
    parser.add_argument(
        "--icon-dir",
        metavar="DIR",
        help="Directory containing icon.png (16×16) and icon@2x.png (32×32). "
             "Defaults to the script's own directory.",
    )
    args = parser.parse_args()

    icon_dir = Path(args.icon_dir) if args.icon_dir else Path(__file__).parent

    session = make_session()

    version = detect_version(session)
    print(f"Detected version: {version}")

    print("Setting up docset structure…")
    setup_docset()
    conn = create_db()

    print("Crawling HTML pages…")
    pages = collect_pages(session)
    print(f"  Found {len(pages)} pages.")

    print("Downloading HTML pages…")
    for i, (url, local) in enumerate(sorted(pages.items()), 1):
        print(f"  [{i:3d}/{len(pages)}] {url}")
        download(session, url, local)
        time.sleep(REQUEST_DELAY)

    print("Collecting static assets…")
    assets = collect_assets(pages)
    print(f"  Found {len(assets)} assets.")

    print("Downloading static assets…")
    for i, (url, local) in enumerate(sorted(assets.items()), 1):
        download(session, url, local, is_html=False)
        if i % 50 == 0:
            print(f"  {i}/{len(assets)}…")
        time.sleep(REQUEST_DELAY)

    index_entries(conn, session)
    conn.close()

    package(icon_dir)


if __name__ == "__main__":
    main()
