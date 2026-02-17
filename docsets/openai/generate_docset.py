#!/usr/bin/env python3
"""Generate a Dash docset for the OpenAI API documentation."""

import os
import re
import sqlite3
import shutil
import subprocess
import urllib.parse

from bs4 import BeautifulSoup

DOCSET_NAME = "OpenAI_API.docset"
DOCUMENTS_PATH = os.path.join(DOCSET_NAME, "Contents/Resources/Documents")
SQLITE_DB_PATH = os.path.join(DOCSET_NAME, "Contents/Resources/docSet.dsidx")
INFO_PLIST_PATH = os.path.join(DOCSET_NAME, "Contents/Info.plist")
DOWNLOAD_DIR = "downloaded_docs"
BASE_URL = "https://developers.openai.com/api/docs/"
ARCHIVE_NAME = "OpenAI_API.tgz"

# All documentation pages to download, organized by category.
# Each entry is (relative_path, display_name, entry_type).
DOC_PAGES = [
    # Getting Started
    ("", "OpenAI API Overview", "Guide"),
    ("quickstart", "Quickstart", "Guide"),
    ("models", "Models", "Guide"),
    ("pricing", "Pricing", "Guide"),
    ("libraries", "Libraries", "Guide"),
    # Core Concepts
    ("guides/text", "Text Generation", "Guide"),
    ("guides/code-generation", "Code Generation", "Guide"),
    ("guides/images-vision", "Images and Vision", "Guide"),
    ("guides/audio", "Audio and Speech", "Guide"),
    ("guides/structured-outputs", "Structured Output", "Guide"),
    ("guides/function-calling", "Function Calling", "Function"),
    ("guides/migrate-to-responses", "Responses API", "Guide"),
    # Agents
    ("guides/agents", "Agents Overview", "Guide"),
    ("guides/agent-builder", "Agent Builder", "Guide"),
    ("guides/node-reference", "Node Reference", "Guide"),
    ("guides/agent-builder-safety", "Agent Builder Safety", "Guide"),
    ("guides/agents-sdk", "Agents SDK", "Guide"),
    ("guides/chatkit", "ChatKit", "Guide"),
    ("guides/chatkit-themes", "Custom Theming", "Guide"),
    ("guides/chatkit-widgets", "Widgets", "Guide"),
    ("guides/chatkit-actions", "Actions", "Guide"),
    ("guides/custom-chatkit", "Advanced Integration", "Guide"),
    ("guides/agent-evals", "Agent Evals", "Guide"),
    ("guides/trace-grading", "Trace Grading", "Guide"),
    ("guides/voice-agents", "Voice Agents", "Guide"),
    # Tools
    ("guides/tools", "Using Tools", "Guide"),
    ("guides/tools-connectors-mcp", "Connectors and MCP", "Guide"),
    ("guides/tools-skills", "Skills", "Guide"),
    ("guides/tools-shell", "Shell", "Guide"),
    ("guides/tools-web-search", "Web Search", "Guide"),
    ("guides/tools-code-interpreter", "Code Interpreter", "Guide"),
    ("guides/tools-file-search", "File Search", "Guide"),
    ("guides/retrieval", "Retrieval", "Guide"),
    ("guides/tools-image-generation", "Image Generation Tool", "Guide"),
    ("guides/tools-computer-use", "Computer Use", "Guide"),
    ("guides/tools-local-shell", "Local Shell Tool", "Guide"),
    ("guides/tools-apply-patch", "Apply Patch", "Guide"),
    # Run and Scale
    ("guides/conversation-state", "Conversation State", "Guide"),
    ("guides/compaction", "Compaction", "Guide"),
    ("guides/background", "Background Mode", "Guide"),
    ("guides/streaming-responses", "Streaming", "Guide"),
    ("guides/webhooks", "Webhooks", "Guide"),
    ("guides/pdf-files", "File Inputs", "Guide"),
    ("guides/prompting", "Prompting Overview", "Guide"),
    ("guides/prompt-caching", "Prompt Caching", "Guide"),
    ("guides/prompt-engineering", "Prompt Engineering", "Guide"),
    ("guides/reasoning", "Reasoning Models", "Guide"),
    ("guides/reasoning-best-practices", "Reasoning Best Practices", "Guide"),
    # Evaluation
    ("guides/evaluation-getting-started", "Evaluation Getting Started", "Guide"),
    ("guides/evals", "Working with Evals", "Guide"),
    ("guides/prompt-optimizer", "Prompt Optimizer", "Guide"),
    ("guides/external-models", "External Models", "Guide"),
    ("guides/evaluation-best-practices", "Evaluation Best Practices", "Guide"),
    # Realtime API
    ("guides/realtime", "Realtime API Overview", "Guide"),
    ("guides/realtime-webrtc", "WebRTC", "Guide"),
    ("guides/realtime-websocket", "WebSocket", "Guide"),
    ("guides/realtime-sip", "SIP", "Guide"),
    ("guides/realtime-models-prompting", "Using Realtime Models", "Guide"),
    ("guides/realtime-conversations", "Managing Conversations", "Guide"),
    ("guides/realtime-server-controls", "Webhooks and Server Controls", "Guide"),
    ("guides/realtime-costs", "Managing Costs", "Guide"),
    ("guides/realtime-transcription", "Realtime Transcription", "Guide"),
    # Model Optimization
    ("guides/model-optimization", "Optimization Cycle", "Guide"),
    ("guides/supervised-fine-tuning", "Supervised Fine-Tuning", "Guide"),
    ("guides/vision-fine-tuning", "Vision Fine-Tuning", "Guide"),
    ("guides/direct-preference-optimization", "Direct Preference Optimization", "Guide"),
    ("guides/reinforcement-fine-tuning", "Reinforcement Fine-Tuning", "Guide"),
    ("guides/rft-use-cases", "RFT Use Cases", "Guide"),
    ("guides/fine-tuning-best-practices", "Fine-Tuning Best Practices", "Guide"),
    ("guides/graders", "Graders", "Guide"),
    # Specialized Models
    ("guides/image-generation", "Image Generation", "Guide"),
    ("guides/video-generation", "Video Generation", "Guide"),
    ("guides/text-to-speech", "Text to Speech", "Guide"),
    ("guides/speech-to-text", "Speech to Text", "Guide"),
    ("guides/deep-research", "Deep Research", "Guide"),
    ("guides/embeddings", "Embeddings", "Guide"),
    ("guides/moderation", "Moderation", "Guide"),
    # Going Live
    ("guides/production-best-practices", "Production Best Practices", "Guide"),
    ("guides/latency-optimization", "Latency Optimization", "Guide"),
    ("guides/predicted-outputs", "Predicted Outputs", "Guide"),
    ("guides/priority-processing", "Priority Processing", "Guide"),
    ("guides/cost-optimization", "Cost Optimization", "Guide"),
    ("guides/batch", "Batch", "Guide"),
    ("guides/flex-processing", "Flex Processing", "Guide"),
    ("guides/optimizing-llm-accuracy", "Accuracy Optimization", "Guide"),
    ("guides/safety-best-practices", "Safety Best Practices", "Guide"),
    ("guides/safety-checks", "Safety Checks", "Guide"),
    # Resources
    ("changelog", "Changelog", "Guide"),
    ("guides/your-data", "Your Data", "Guide"),
    ("guides/rbac", "Permissions", "Guide"),
    ("guides/rate-limits", "Rate Limits", "Guide"),
    ("deprecations", "Deprecations", "Guide"),
    ("guides/developer-mode", "Developer Mode", "Guide"),
    # ChatGPT Actions
    ("actions/introduction", "Actions Introduction", "Guide"),
    ("actions/getting-started", "Actions Quickstart", "Guide"),
    ("actions/actions-library", "Actions Library", "Guide"),
    ("actions/authentication", "Actions Authentication", "Guide"),
    ("actions/production", "Actions Production", "Guide"),
    ("actions/data-retrieval", "Actions Data Retrieval", "Guide"),
    ("actions/sending-files", "Actions Sending Files", "Guide"),
    # Legacy
    ("assistants/migration", "Assistants Migration", "Guide"),
    ("assistants/deep-dive", "Assistants Deep Dive", "Guide"),
    ("assistants/tools", "Assistants Tools", "Guide"),
    # Latest model
    ("guides/latest-model", "Latest Model: GPT-5.2", "Guide"),
]


def download_docs():
    """Download documentation pages using wget."""
    print("Downloading OpenAI API documentation...")

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
                "--level=2",                # limit depth
                "-q",                       # quiet
                "--wait=0.5",               # be polite
                "--random-wait",
                "-e", "robots=off",
                "--reject", "*.zip,*.tar.gz,*.whl,*.exe",
                "--reject-regex", r".*[@?].*=.*",
                "-I", "/api/docs/,/static/,/_next/",
                "-P", DOWNLOAD_DIR,
                BASE_URL,
            ],
            check=False,
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
    source = os.path.join(DOWNLOAD_DIR, "api", "docs")
    if not os.path.exists(source):
        source = os.path.join(DOWNLOAD_DIR, "api")
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

    # Remove redirect and localized pages
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for f in files:
            if f.endswith(".html"):
                fpath = os.path.join(root, f)
                relpath = os.path.relpath(fpath, DOCUMENTS_PATH)
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
    <string>openai-api</string>
    <key>CFBundleName</key>
    <string>OpenAI API</string>
    <key>DocSetPlatformFamily</key>
    <string>openai</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>index.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
    <key>isJavaScriptEnabled</key>
    <true/>
    <key>DashDocSetFallbackURL</key>
    <string>https://developers.openai.com/api/docs/</string>
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
    normalized = relpath.replace("\\", "/")
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

            modified = False
            for h in soup.find_all(["h2", "h3"]):
                hid = h.get("id")
                if not hid:
                    continue
                if h.find("a", class_="dashAnchor"):
                    continue

                heading_text = h.get_text().strip()
                heading_text = re.sub(r"[¶#\s]+$", "", heading_text)
                if not heading_text:
                    continue

                add_dash_anchor(h, "Section", heading_text)
                modified = True

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
.sidebar, .top-nav, .site-header,
.site-footer, .footer,
.search-form, .search-bar,
.breadcrumb, .breadcrumbs,
.page-rating, .feedback-widget,
.cookie-notification, .cookie-banner,
[data-is-touch-wrapper] {
    display: none !important;
}

main, article,
.main-content, .article-body {
    margin: 0 auto !important;
    padding: 16px !important;
    max-width: 100% !important;
}

body {
    margin: 0 !important;
    padding: 0 !important;
}
"""
    css_injected = False
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for fname in files:
            if fname.endswith(".css") and ("main" in fname.lower() or "app" in fname.lower()):
                css_path = os.path.join(root, fname)
                with open(css_path, "a") as f:
                    f.write(dash_css)
                css_injected = True
                print(f"Injected Dash CSS into {os.path.relpath(css_path, DOCUMENTS_PATH)}")
                return

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
    print("=== OpenAI API Dash Docset Generator ===\n")

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
