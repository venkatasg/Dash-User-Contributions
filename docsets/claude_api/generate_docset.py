#!/usr/bin/env python3
"""Generate a Dash docset for the Claude (Anthropic) API Reference."""

import os
import re
import sqlite3
import shutil
import subprocess
import urllib.parse

from bs4 import BeautifulSoup

DOCSET_NAME = "Claude_API.docset"
DOCUMENTS_PATH = os.path.join(DOCSET_NAME, "Contents/Resources/Documents")
SQLITE_DB_PATH = os.path.join(DOCSET_NAME, "Contents/Resources/docSet.dsidx")
INFO_PLIST_PATH = os.path.join(DOCSET_NAME, "Contents/Info.plist")
DOWNLOAD_DIR = "downloaded_docs"
BASE_URL = "https://platform.claude.com/docs/en/api/"
ARCHIVE_NAME = "Claude_API.tgz"

# API Reference pages only.
# Each entry is (relative_path, display_name, entry_type).
# Entry types use Dash-supported types:
#   Guide     - overview/introductory pages
#   Method    - API endpoint pages (POST/GET/DELETE etc.)
#   Resource  - resource grouping pages
#   Library   - SDK pages
#   Setting   - configuration/versioning pages
#   Error     - error reference
#   Event     - streaming events
#   Sample    - example pages
#   Section   - sub-headings within pages (auto-generated)
DOC_PAGES = [
    # API Overview
    ("overview", "API Overview", "Guide"),
    ("beta-headers", "Beta Headers", "Setting"),
    ("errors", "Errors", "Error"),
    ("rate-limits", "Rate Limits", "Setting"),
    ("service-tiers", "Service Tiers", "Setting"),
    ("versioning", "API Versioning", "Setting"),
    ("ip-addresses", "IP Addresses", "Setting"),
    ("supported-regions", "Supported Regions", "Setting"),
    ("openai-sdk", "OpenAI SDK Compatibility", "Guide"),
    # Client SDKs
    ("client-sdks", "Client SDKs", "Guide"),
    ("sdks/python", "Python SDK", "Library"),
    ("sdks/typescript", "TypeScript SDK", "Library"),
    ("sdks/java", "Java SDK", "Library"),
    ("sdks/go", "Go SDK", "Library"),
    ("sdks/ruby", "Ruby SDK", "Library"),
    ("sdks/csharp", "C# SDK", "Library"),
    ("sdks/php", "PHP SDK", "Library"),
    # Messages API
    ("messages", "POST /v1/messages", "Method"),
    ("messages-streaming", "Messages Streaming", "Event"),
    ("messages-examples", "Messages Examples", "Sample"),
    ("messages-count-tokens", "POST /v1/messages/count_tokens", "Method"),
    # Message Batches API
    ("creating-message-batches", "POST /v1/messages/batches", "Method"),
    ("retrieving-message-batches", "GET /v1/messages/batches/:id", "Method"),
    ("listing-message-batches", "GET /v1/messages/batches", "Method"),
    ("canceling-message-batches", "POST /v1/messages/batches/:id/cancel", "Method"),
    ("retrieving-message-batch-results", "GET /v1/messages/batches/:id/results", "Method"),
    ("deleting-message-batches", "DELETE /v1/messages/batches/:id", "Method"),
    # Models API
    ("models-list", "GET /v1/models", "Method"),
    ("models-get", "GET /v1/models/:id", "Method"),
    # Files API
    ("files-create", "POST /v1/files", "Method"),
    ("files-list", "GET /v1/files", "Method"),
    ("files-get", "GET /v1/files/:id", "Method"),
    ("files-delete", "DELETE /v1/files/:id", "Method"),
    ("files-download", "GET /v1/files/:id/content", "Method"),
    # Skills API
    ("skills/create-skill", "POST /v1/skills", "Method"),
    ("skills/list-skills", "GET /v1/skills", "Method"),
    ("skills/get-skill", "GET /v1/skills/:id", "Method"),
    ("skills/update-skill", "PUT /v1/skills/:id", "Method"),
    ("skills/delete-skill", "DELETE /v1/skills/:id", "Method"),
]


def download_docs():
    """Download API reference pages using wget."""
    print("Downloading Claude API reference...")

    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        subprocess.run(
            [
                "wget",
                "-r",                       # recursive download
                "-np",                      # no parent
                "-k",                       # convert links for local viewing
                "-p",                       # get page requisites (CSS, JS, images)
                "-E",                       # adjust extensions
                "--adjust-extension",
                "--restrict-file-names=windows",
                "-nH",                      # no host directory
                "--level=3",
                "-q",                       # quiet
                "--wait=0.5",
                "--random-wait",
                "-e", "robots=off",
                "--reject", "*.zip,*.tar.gz,*.whl,*.exe",
                "--reject-regex", r".*(/(de|es|fr|it|ja|ko|pt|zh)/).*",
                "-I", "/docs/en/api/,/static/,/_next/",
                "-P", DOWNLOAD_DIR,
                BASE_URL,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
        print("API reference downloaded successfully.")
    except FileNotFoundError:
        print("Error: wget not found. Please install wget:")
        print("  Ubuntu/Debian: sudo apt-get install wget")
        print("  macOS: brew install wget")
        raise
    except subprocess.TimeoutExpired:
        print("Warning: wget timed out. Continuing with what was downloaded.")


def setup_structure():
    """Create the docset directory structure."""
    if os.path.exists(DOCSET_NAME):
        shutil.rmtree(DOCSET_NAME)
    os.makedirs(DOCUMENTS_PATH)


def copy_docs():
    """Copy downloaded documentation into the docset."""
    source = os.path.join(DOWNLOAD_DIR, "docs", "en", "api")
    if not os.path.exists(source):
        source = os.path.join(DOWNLOAD_DIR, "docs", "en")
        if not os.path.exists(source):
            print(f"Warning: Expected source docs at {source}")
            for root, dirs, files in os.walk(DOWNLOAD_DIR):
                if any(f.endswith(".html") for f in files):
                    source = root
                    print(f"Found HTML files at: {source}")
                    break

    if os.path.exists(source):
        for item in os.listdir(source):
            s = os.path.join(source, item)
            d = os.path.join(DOCUMENTS_PATH, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

    # Copy static assets
    for static_name in ["static", "_next"]:
        static_dir = os.path.join(DOWNLOAD_DIR, static_name)
        if os.path.exists(static_dir):
            dest_static = os.path.join(DOCUMENTS_PATH, f"_{static_name}")
            shutil.copytree(static_dir, dest_static, dirs_exist_ok=True)

    # Remove redirect, non-English, and non-API pages
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for f in files:
            if f.endswith(".html"):
                fpath = os.path.join(root, f)
                if "@" in f or "?" in f:
                    os.remove(fpath)
                    continue
                try:
                    with open(fpath, "r", errors="replace") as fh:
                        content = fh.read(1000)
                    if "<title>Redirecting" in content or 'http-equiv="refresh"' in content:
                        os.remove(fpath)
                except Exception:
                    pass


def create_plist():
    """Create the Info.plist file for the docset."""
    plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>claude-api</string>
    <key>CFBundleName</key>
    <string>Claude API</string>
    <key>DocSetPlatformFamily</key>
    <string>claude</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>overview.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
    <key>isJavaScriptEnabled</key>
    <true/>
    <key>DashDocSetFallbackURL</key>
    <string>https://platform.claude.com/docs/en/api/</string>
    <key>DashDocSetDefaultFTSEnabled</key>
    <true/>
</dict>
</plist>
"""
    with open(INFO_PLIST_PATH, "w") as f:
        f.write(plist_content)


def add_dash_anchor(tag, entry_type, name):
    """Insert a Dash anchor element before the given tag."""
    safe_name = urllib.parse.quote(name, safe="")
    anchor_name = f"//apple_ref/cpp/{entry_type}/{safe_name}"
    anchor = BeautifulSoup(
        f'<a name="{anchor_name}" class="dashAnchor"></a>', "html.parser"
    ).a
    tag.insert(0, anchor)


def classify_heading(heading_text):
    """Determine the Dash entry type for a heading based on its content."""
    lower = heading_text.lower()

    # HTTP method patterns
    if re.match(r"^(get|post|put|patch|delete|head|options)\s+/", lower):
        return "Method"

    # Parameter-like headings
    if any(kw in lower for kw in ["parameter", "request body", "query param",
                                   "path param", "header param", "body param"]):
        return "Parameter"

    # Response/return type headings
    if any(kw in lower for kw in ["response", "returns", "return type"]):
        return "Value"

    # Object/type definitions
    if any(kw in lower for kw in ["object", "schema", "enum"]):
        return "Type"

    # Error headings
    if any(kw in lower for kw in ["error", "status code"]):
        return "Error"

    # Event headings
    if any(kw in lower for kw in ["event", "streaming"]):
        return "Event"

    # Example headings
    if any(kw in lower for kw in ["example", "sample", "usage"]):
        return "Sample"

    return "Section"


def get_page_category(relpath):
    """Determine the entry type based on file path."""
    normalized = relpath.replace("\\", "/")
    if normalized.endswith("/index.html"):
        normalized = normalized[: -len("/index.html")]
    elif normalized.endswith(".html"):
        normalized = normalized[: -len(".html")]

    for page_path, display_name, entry_type in DOC_PAGES:
        if normalized == page_path or normalized.rstrip("/") == page_path:
            return display_name, entry_type

    # Fallback classification based on path patterns
    if any(kw in normalized for kw in ["create", "list", "get", "delete",
                                        "retrieve", "update", "cancel"]):
        return None, "Method"

    return None, "Guide"


def index_docs():
    """Create the SQLite search index and add Dash anchors to HTML files."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE searchIndex("
        "id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);"
    )
    cur.execute("CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);")

    indexed_count = 0

    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for fname in files:
            if not fname.endswith(".html"):
                continue
            if fname == "404.html":
                continue

            abspath = os.path.join(root, fname)
            relpath = os.path.relpath(abspath, DOCUMENTS_PATH)

            # Skip static asset HTML files
            if relpath.startswith("_static") or relpath.startswith("_next"):
                continue

            try:
                with open(abspath, "r", errors="replace") as f:
                    soup = BeautifulSoup(f, "html.parser")
            except Exception as e:
                print(f"Error parsing {relpath}: {e}")
                continue

            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else None

            if title:
                title = re.split(r"\s+\|\s+", title)[0].strip()
                for sep in [" - ", " \u2013 ", " :: "]:
                    if sep in title:
                        title = title.split(sep)[0].strip()
                        break

            if not title or title in ("Redirecting...", ""):
                continue

            display_name, entry_type = get_page_category(relpath)
            if display_name:
                title = display_name

            cur.execute(
                "INSERT OR IGNORE INTO searchIndex(name, type, path) "
                "VALUES (?, ?, ?)",
                (title, entry_type, relpath),
            )
            indexed_count += 1

            # Index headings within the page for table of contents
            modified = False
            for h in soup.find_all(["h1", "h2", "h3"]):
                hid = h.get("id")
                if not hid:
                    continue
                if h.find("a", class_="dashAnchor"):
                    continue

                heading_text = h.get_text().strip()
                heading_text = re.sub(r"[¶#\s]+$", "", heading_text)
                if not heading_text:
                    continue

                heading_type = classify_heading(heading_text)
                add_dash_anchor(h, heading_type, heading_text)
                modified = True

            if modified:
                try:
                    with open(abspath, "w", errors="replace") as f:
                        f.write(str(soup))
                except Exception as e:
                    print(f"Error writing {relpath}: {e}")

    conn.commit()
    conn.close()
    print(f"Indexed {indexed_count} pages.")


def inject_dash_css():
    """Inject minimal CSS to hide navigation elements for Dash display.

    Only hides sidebar, topbar, and search elements. Does not override
    the main content styling to preserve the original appearance.
    """
    dash_css = """
/* Dash docset: hide navigation chrome only */
#mintlify-sidebar,
.mint-sidebar,
.mint-header,
.mint-footer,
header[role="banner"],
nav[role="navigation"],
.sidebar,
.top-nav,
.site-header,
.site-footer,
.search-form,
.search-bar,
input[type="search"],
.breadcrumb,
.breadcrumbs,
.feedback-widget,
.page-rating,
.cookie-notification,
.cookie-banner,
[data-is-touch-wrapper] > nav,
button[aria-label="Search"],
div[id*="search"],
div[class*="search-overlay"] {
    display: none !important;
}

/* Expand main content to fill available width */
main,
.main-content,
article {
    margin-left: 0 !important;
    max-width: 100% !important;
    width: 100% !important;
}
"""
    # Inject as <style> tag in every HTML file for reliability
    style_tag = f"<style>{dash_css}</style>"
    count = 0
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for fname in files:
            if fname.endswith(".html"):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", errors="replace") as f:
                        content = f.read()
                    if "</head>" in content:
                        content = content.replace("</head>", style_tag + "</head>", 1)
                    else:
                        content = style_tag + content
                    with open(fpath, "w", errors="replace") as f:
                        f.write(content)
                    count += 1
                except Exception:
                    pass
    print(f"Injected Dash CSS into {count} HTML files.")


def package_docset():
    """Create a compressed archive of the docset."""
    if os.path.exists(ARCHIVE_NAME):
        os.remove(ARCHIVE_NAME)
    subprocess.run(
        ["tar", "--exclude=.DS_Store", "-czf", ARCHIVE_NAME, DOCSET_NAME],
        check=True,
    )
    size_mb = os.path.getsize(ARCHIVE_NAME) / (1024 * 1024)
    print(f"Created {ARCHIVE_NAME} ({size_mb:.1f} MB)")


def cleanup():
    """Remove the download directory."""
    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    print("Cleaned up downloaded files.")


if __name__ == "__main__":
    print("=== Claude API Reference Dash Docset Generator ===\n")

    print("[1/7] Downloading API reference...")
    download_docs()

    print("\n[2/7] Setting up docset structure...")
    setup_structure()

    print("\n[3/7] Copying documentation...")
    copy_docs()

    print("\n[4/7] Creating Info.plist...")
    create_plist()

    print("\n[5/7] Indexing documentation and adding Dash anchors...")
    index_docs()

    print("\n[6/7] Injecting Dash CSS refinements...")
    inject_dash_css()

    print("\n[7/7] Packaging docset...")
    package_docset()

    print("\nDone! Docset archive: " + ARCHIVE_NAME)
    print("To install: open " + ARCHIVE_NAME + " with Dash, or")
    print("copy " + DOCSET_NAME + " to ~/Library/Application Support/Dash/DocSets/")
