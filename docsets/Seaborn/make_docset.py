#!/usr/bin/env python3
"""
Generate the seaborn Dash docset from seaborn.pydata.org.

Dependencies (install with pip):
    requests
    beautifulsoup4

Usage:
    python make_docset.py [--icon-dir DIR]

    --icon-dir DIR   Directory that contains icon.png (16x16) and
                     icon@2x.png (32x32). Defaults to the directory
                     containing this script.

The script produces seaborn.tgz in the current working directory.
It removes the header navigation bar and both sidebars so pages
render cleanly inside the Dash app.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import tarfile
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://seaborn.pydata.org/"
DOCSET_NAME = "seaborn"
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
/* ── Dash docset: hide navigation elements ── */
nav.bd-header,
#navbar-main,
.bd-sidebar-primary,
.bd-sidebar-secondary,
.bd-toc,
input.sidebar-toggle,
label.overlay,
.search-button__wrapper,
.prev-next-area,
.pst-footer-article-navigation,
#pst-back-to-top {
    display: none !important;
}

/* Expand the main content to fill the full page width */
.bd-container__inner {
    display: block !important;
}

.bd-content {
    max-width: 100% !important;
    flex: unset !important;
}

/* Remove top padding that was reserved for the fixed navbar */
body {
    padding-top: 0 !important;
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
    <string>seaborn</string>
    <key>CFBundleName</key>
    <string>seaborn</string>
    <key>DocSetPlatformFamily</key>
    <string>seaborn</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>index.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
</dict>
</plist>
"""

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "seaborn-docset-generator/1.0 "
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

    Query strings and fragments are ignored. A bare directory URL
    gets ``index.html`` appended.
    """
    path = urllib.parse.urlparse(url).path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    return Path(path)


def resolve(href: str, page_url: str) -> str | None:
    """
    Resolve *href* (possibly relative) against *page_url*.

    Returns the absolute URL without query string/fragment,
    or ``None`` if the URL should be skipped (external, anchor-only, …).
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

    1. Inject DASH_CSS into ``<head>`` to hide navigation.
    2. Strip query strings from local asset ``href``/``src`` attributes
       so they match the filenames we save on disk.
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
    session: requests.Session,
    url: str,
    local: Path,
    *,
    html: bool = True,
) -> bool:
    """
    Fetch *url* and save to *local*.

    For HTML files (``html=True``) the content passes through
    :func:`process_html` first.  Binary files are saved verbatim.
    Already-existing files are skipped.

    Returns ``True`` on success.
    """
    if local.exists():
        return True

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"    SKIP {url}  ({exc})")
        return False

    local.parent.mkdir(parents=True, exist_ok=True)
    ctype = resp.headers.get("content-type", "")
    if html and ("text/html" in ctype or local.suffix == ".html"):
        local.write_text(process_html(resp.text, url), encoding="utf-8")
    else:
        local.write_bytes(resp.content)
    return True


def collect_pages(session: requests.Session) -> dict[str, Path]:
    """
    Crawl the seaborn docs site starting from a set of seed URLs and
    return every HTML page that belongs to the site.

    Returns ``{absolute_url: local_path}`` (local paths inside DOCS_DIR).
    """
    queue: set[str] = set()
    seen: set[str] = set()
    pages: dict[str, Path] = {}

    def enqueue(url: str) -> None:
        url = strip_query(url)
        if url.startswith(BASE_URL) and url not in seen and url not in queue:
            queue.add(url)

    # Seed pages
    for rel in (
        "",
        "api.html",
        "tutorial.html",
        "installing.html",
        "faq.html",
        "citing.html",
        "whatsnew/latest.html",
    ):
        enqueue(BASE_URL + rel)

    while queue:
        url = queue.pop()
        seen.add(url)
        local = DOCS_DIR / url_to_local(url)
        pages[url] = local

        # Only follow links from HTML-like pages
        if not (url.endswith(".html") or url.endswith("/")):
            continue

        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
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
    Scan already-saved HTML files and collect every CSS / JS / image URL
    that belongs to the seaborn docs site.

    Returns ``{absolute_url: local_path}``.
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


def _entry_type(full_name: str) -> str:
    """
    Heuristically map a seaborn symbol name to a Dash entry type.

    seaborn uses:
      - ``Function`` for plot functions (lowercase first letter)
      - ``Class``    for grid/objects classes (uppercase first letter)
      - ``Method``   for methods on objects-interface classes
                     (four or more dotted components)
    """
    parts = full_name.split(".")
    last = parts[-1]

    # Four or more components → seaborn.objects.SomeClass.some_method
    if len(parts) >= 4:
        return "Method"

    # Uppercase first letter of the last component → Class
    if last and last[0].isupper():
        return "Class"

    return "Function"


def index_entries(conn: sqlite3.Connection, session: requests.Session) -> None:
    """
    Fetch ``api.html``, parse every link into the ``generated/`` subtree,
    and insert each symbol into the Dash search index.
    """
    print("Indexing API entries…")
    try:
        resp = session.get(BASE_URL + "api.html", timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  Could not fetch api.html: {exc}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    cur = conn.cursor()
    count = 0

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if not href.startswith("generated/seaborn"):
            continue

        name = a.get_text(strip=True)
        if not name:
            continue

        path = href.split("#")[0]
        fragment = href.split("#")[1] if "#" in href else None
        full_path = path + (f"#{fragment}" if fragment else "")

        try:
            cur.execute(
                "INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?, ?, ?)",
                (name, _entry_type(name), full_path),
            )
            count += 1
        except sqlite3.Error:
            pass

    conn.commit()
    print(f"  Indexed {count} entries.")


# ---------------------------------------------------------------------------
# Packaging
# ---------------------------------------------------------------------------


def package(icon_dir: Path | None = None) -> None:
    """
    Copy icons into the docset (if found) and create ``seaborn.tgz``.
    """
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
        description="Build the seaborn Dash docset from seaborn.pydata.org"
    )
    parser.add_argument(
        "--icon-dir",
        metavar="DIR",
        help="Directory containing icon.png (16×16) and icon@2x.png (32×32). "
             "Defaults to the script's own directory.",
    )
    args = parser.parse_args()

    # Resolve icon directory (default: same directory as this script)
    icon_dir = Path(args.icon_dir) if args.icon_dir else Path(__file__).parent

    session = make_session()

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
        download(session, url, local, html=False)
        if i % 50 == 0:
            print(f"  {i}/{len(assets)}…")
        time.sleep(REQUEST_DELAY)

    index_entries(conn, session)
    conn.close()

    package(icon_dir)


if __name__ == "__main__":
    main()
