#!/usr/bin/env python3
"""Generate a Dash docset for the Google Gemini API documentation."""

import os
import re
import sqlite3
import shutil
import subprocess
import urllib.parse

from bs4 import BeautifulSoup

DOCSET_NAME = "Gemini_API.docset"
DOCUMENTS_PATH = os.path.join(DOCSET_NAME, "Contents/Resources/Documents")
SQLITE_DB_PATH = os.path.join(DOCSET_NAME, "Contents/Resources/docSet.dsidx")
INFO_PLIST_PATH = os.path.join(DOCSET_NAME, "Contents/Info.plist")
DOWNLOAD_DIR = "downloaded_docs"
SOURCE_DOCS = os.path.join(DOWNLOAD_DIR, "gemini-api/docs")
BASE_URL = "https://ai.google.dev/gemini-api/docs/"
ARCHIVE_NAME = "Gemini_API.tgz"

# All documentation pages to download, organized by category.
# Each entry is (relative_path, display_name, entry_type).
DOC_PAGES = [
    # Get Started
    ("", "Gemini API Overview", "Guide"),
    ("quickstart", "Quickstart", "Guide"),
    ("api-key", "API Keys", "Guide"),
    ("libraries", "Libraries", "Guide"),
    ("interactions", "Interactions API", "Guide"),
    # Models
    ("models", "Gemini Models", "Guide"),
    ("gemini-3", "Gemini 3", "Guide"),
    ("image-generation", "Image Generation", "Guide"),
    ("video", "Video Generation", "Guide"),
    ("music-generation", "Music Generation", "Guide"),
    ("imagen", "Imagen", "Guide"),
    ("embeddings", "Embeddings", "Guide"),
    ("robotics-overview", "Robotics", "Guide"),
    ("speech-generation", "Text-to-Speech", "Guide"),
    ("pricing", "Pricing", "Guide"),
    ("rate-limits", "Rate Limits", "Guide"),
    # Core Capabilities
    ("text-generation", "Text Generation", "Guide"),
    ("image-understanding", "Image Understanding", "Guide"),
    ("video-understanding", "Video Understanding", "Guide"),
    ("document-processing", "Document Processing", "Guide"),
    ("audio", "Audio Understanding", "Guide"),
    ("thinking", "Thinking", "Guide"),
    ("thought-signatures", "Thought Signatures", "Guide"),
    ("structured-output", "Structured Output", "Guide"),
    ("function-calling", "Function Calling", "Function"),
    ("long-context", "Long Context", "Guide"),
    # Tools and Agents
    ("tools", "Tools Overview", "Guide"),
    ("deep-research", "Deep Research", "Guide"),
    ("google-search", "Google Search", "Guide"),
    ("maps-grounding", "Google Maps", "Guide"),
    ("code-execution", "Code Execution", "Guide"),
    ("url-context", "URL Context", "Guide"),
    ("computer-use", "Computer Use", "Guide"),
    ("file-search", "File Search", "Guide"),
    # Live API
    ("live", "Live API", "Guide"),
    ("live-guide", "Live API Capabilities", "Guide"),
    ("live-tools", "Live API Tool Use", "Guide"),
    ("live-session", "Live API Session Management", "Guide"),
    ("ephemeral-tokens", "Ephemeral Tokens", "Guide"),
    # Guides
    ("batch-api", "Batch API", "Guide"),
    ("file-input-methods", "Input Methods", "Guide"),
    ("files", "Files API", "Guide"),
    ("caching", "Context Caching", "Guide"),
    ("openai", "OpenAI Compatibility", "Guide"),
    ("media-resolution", "Media Resolution", "Guide"),
    ("tokens", "Token Counting", "Guide"),
    ("prompting-strategies", "Prompt Engineering", "Guide"),
    ("logs-datasets", "Logs and Datasets", "Guide"),
    ("logs-policy", "Data Logging and Sharing", "Guide"),
    ("safety-settings", "Safety Settings", "Guide"),
    ("safety-guidance", "Safety Guidance", "Guide"),
    # Frameworks
    ("langgraph-example", "LangChain & LangGraph", "Guide"),
    ("crewai-example", "CrewAI", "Guide"),
    ("llama-index", "LlamaIndex", "Guide"),
    ("vercel-ai-sdk-example", "Vercel AI SDK", "Guide"),
    # Resources
    ("migrate", "Migrate to Gen AI SDK", "Guide"),
    ("changelog", "Release Notes", "Guide"),
    ("deprecations", "Deprecations", "Guide"),
    ("troubleshooting", "API Troubleshooting", "Guide"),
    ("billing", "Billing", "Guide"),
    ("partner-integration", "Partner Integrations", "Guide"),
    # Google AI Studio
    ("ai-studio-quickstart", "AI Studio Quickstart", "Guide"),
    ("aistudio-build-mode", "AI Studio Build Mode", "Guide"),
    ("learnlm", "LearnLM", "Guide"),
    ("troubleshoot-ai-studio", "AI Studio Troubleshooting", "Guide"),
    ("workspace", "Workspace Access", "Guide"),
    # Google Cloud
    ("migrate-to-cloud", "Vertex AI Gemini API", "Guide"),
    ("oauth", "OAuth Authentication", "Guide"),
    # Policies
    ("available-regions", "Available Regions", "Guide"),
    ("usage-policies", "Usage Policies", "Guide"),
    ("feedback-policies", "Feedback Policies", "Guide"),
]


def download_docs():
    """Download documentation pages using wget."""
    print("Downloading Gemini API documentation...")

    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Use wget to mirror the docs site, restricted to /gemini-api/docs/
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
                "--level=2",                # limit depth to avoid crawling too far
                "-q",                       # quiet
                "--wait=0.5",               # be polite: wait between requests
                "--random-wait",
                "-e", "robots=off",         # ignore robots.txt for documentation
                "--reject", "*.zip,*.tar.gz,*.whl,*.exe",
                "--reject-regex", r".*[@?].*=.*",   # skip localized/variant pages
                "-I", "/gemini-api/docs/,/static/",  # only these paths
                "-P", DOWNLOAD_DIR,
                BASE_URL,
            ],
            check=False,  # wget returns non-zero on some warnings
            capture_output=True,
            text=True,
            timeout=600,
        )
        print("Documentation downloaded successfully.")
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
    source = os.path.join(DOWNLOAD_DIR, "gemini-api", "docs")
    if not os.path.exists(source):
        # Try alternate structure
        source = os.path.join(DOWNLOAD_DIR, "gemini-api")
        if not os.path.exists(source):
            print(f"Warning: Expected source docs at {source}")
            # Try to find the docs wherever wget put them
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

    # Also copy static assets if they exist
    static_dir = os.path.join(DOWNLOAD_DIR, "static")
    if os.path.exists(static_dir):
        dest_static = os.path.join(DOCUMENTS_PATH, "_static")
        shutil.copytree(static_dir, dest_static, dirs_exist_ok=True)

    # Remove redirect pages and localized pages
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for f in files:
            if f.endswith(".html"):
                fpath = os.path.join(root, f)
                relpath = os.path.relpath(fpath, DOCUMENTS_PATH)
                # Remove localized and variant pages
                # (e.g. text-generation@hl=de.html, text-generation@lang=python.html)
                if "@" in f or "?" in f:
                    print(f"Removing localized page: {relpath}")
                    os.remove(fpath)
                    continue
                try:
                    with open(fpath, "r", errors="replace") as fh:
                        content = fh.read(1000)
                    if "<title>Redirecting" in content or 'http-equiv="refresh"' in content:
                        print(f"Removing redirect page: {relpath}")
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
    <string>gemini-api</string>
    <key>CFBundleName</key>
    <string>Gemini API</string>
    <key>DocSetPlatformFamily</key>
    <string>gemini</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>index.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
    <key>isJavaScriptEnabled</key>
    <true/>
    <key>DashDocSetFallbackURL</key>
    <string>https://ai.google.dev/gemini-api/docs/</string>
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


def get_page_category(relpath):
    """Determine the entry type based on file path."""
    # Look up in DOC_PAGES for specific type assignments
    normalized = relpath.replace("\\", "/")
    # Strip index.html from path
    if normalized.endswith("/index.html"):
        normalized = normalized[: -len("/index.html")]
    elif normalized.endswith(".html"):
        normalized = normalized[: -len(".html")]

    for page_path, display_name, entry_type in DOC_PAGES:
        if normalized == page_path or normalized.rstrip("/") == page_path:
            return display_name, entry_type

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

            try:
                with open(abspath, "r", errors="replace") as f:
                    soup = BeautifulSoup(f, "html.parser")
            except Exception as e:
                print(f"Error parsing {relpath}: {e}")
                continue

            # Get page title
            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else None

            if title:
                # Clean up title: remove site name suffixes like
                # "Text generation  |  Gemini API  |  Google AI for Developers"
                # The separator may have varying whitespace around |
                title = re.split(r"\s+\|\s+", title)[0].strip()
                # Also handle other separator styles
                for sep in [" - ", " \u2013 ", " :: "]:
                    if sep in title:
                        title = title.split(sep)[0].strip()
                        break

            if not title or title in ("Redirecting...", ""):
                continue

            # Get the category and type for this page
            display_name, entry_type = get_page_category(relpath)
            if display_name:
                title = display_name

            # Insert main page entry
            cur.execute(
                "INSERT OR IGNORE INTO searchIndex(name, type, path) "
                "VALUES (?, ?, ?)",
                (title, entry_type, relpath),
            )
            indexed_count += 1

            # Index headings within the page for table of contents
            modified = False
            for h in soup.find_all(["h2", "h3"]):
                hid = h.get("id")
                if not hid:
                    continue
                if h.find("a", class_="dashAnchor"):
                    continue

                heading_text = h.get_text().strip()
                # Remove trailing anchor characters like ¶ or #
                heading_text = re.sub(r"[¶#\s]+$", "", heading_text)
                if not heading_text:
                    continue

                anchor_path = f"{relpath}#{hid}"
                add_dash_anchor(h, "Section", heading_text)
                modified = True

            # Also add TOC anchors for h1
            for h in soup.find_all(["h1"]):
                hid = h.get("id")
                if hid and not h.find("a", class_="dashAnchor"):
                    heading_text = h.get_text().strip()
                    heading_text = re.sub(r"[¶#\s]+$", "", heading_text)
                    if heading_text:
                        add_dash_anchor(h, "Section", heading_text)
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
    """Inject CSS to hide navigation elements that aren't useful in Dash."""
    dash_css = """
/* Dash docset refinements - hide site navigation elements */
header, nav,
[role="navigation"],
.devsite-header, .devsite-top-nav,
.devsite-sidebar, .devsite-toc,
.devsite-footer, .devsite-banner,
.devsite-search-form,
.devsite-nav, .devsite-book-nav,
.devsite-breadcrumb-list,
.devsite-page-rating,
.devsite-feedback,
.cookie-notification,
[data-is-touch-wrapper],
.glue-cookie-notification-bar {
    display: none !important;
}

.devsite-main-content,
.devsite-article-body,
article {
    margin: 0 auto !important;
    padding: 16px !important;
    max-width: 100% !important;
}

body {
    margin: 0 !important;
    padding: 0 !important;
}
"""
    # Try to find an existing CSS file to append to
    css_injected = False
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for fname in files:
            if fname.endswith(".css") and "devsite" in fname.lower():
                css_path = os.path.join(root, fname)
                with open(css_path, "a") as f:
                    f.write(dash_css)
                css_injected = True
                print(f"Injected Dash CSS into {os.path.relpath(css_path, DOCUMENTS_PATH)}")
                return

    # If no devsite CSS found, inject into every HTML file as <style> tag
    if not css_injected:
        style_tag = f"<style>{dash_css}</style>"
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
                    except Exception:
                        pass
        print("Injected Dash CSS into all HTML files.")


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
    print("=== Gemini API Dash Docset Generator ===\n")

    print("[1/7] Downloading documentation...")
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
