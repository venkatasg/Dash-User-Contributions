#!/usr/bin/env python3
"""Generate a Dash docset for the Claude (Anthropic) API documentation."""

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
BASE_URL = "https://platform.claude.com/docs/en/"
ARCHIVE_NAME = "Claude_API.tgz"

# All documentation pages to download, organized by category.
# Each entry is (relative_path, display_name, entry_type).
DOC_PAGES = [
    # Getting Started
    ("home", "Claude Documentation Home", "Guide"),
    ("intro", "Introduction", "Guide"),
    ("get-started", "Get Started", "Guide"),
    # About Claude - Models
    ("about-claude/models/overview", "Models Overview", "Guide"),
    ("about-claude/models/choosing-a-model", "Choosing a Model", "Guide"),
    ("about-claude/models/whats-new-claude-4-6", "What's New in Claude 4.6", "Guide"),
    ("about-claude/models/migration-guide", "Migration Guide", "Guide"),
    ("about-claude/model-deprecations", "Model Deprecations", "Guide"),
    ("about-claude/pricing", "Pricing", "Guide"),
    # About Claude - Use Case Guides
    ("about-claude/use-case-guides/overview", "Use Case Guides", "Guide"),
    ("about-claude/use-case-guides/ticket-routing", "Ticket Routing", "Guide"),
    ("about-claude/use-case-guides/customer-support-chat", "Customer Support Chat", "Guide"),
    ("about-claude/use-case-guides/content-moderation", "Content Moderation", "Guide"),
    ("about-claude/use-case-guides/legal-summarization", "Legal Summarization", "Guide"),
    # Build with Claude - Core
    ("build-with-claude/overview", "Features Overview", "Guide"),
    ("build-with-claude/working-with-messages", "Working with Messages", "Guide"),
    ("build-with-claude/handling-stop-reasons", "Handling Stop Reasons", "Guide"),
    ("build-with-claude/extended-thinking", "Extended Thinking", "Guide"),
    ("build-with-claude/adaptive-thinking", "Adaptive Thinking", "Guide"),
    ("build-with-claude/effort", "Effort", "Guide"),
    ("build-with-claude/fast-mode", "Fast Mode", "Guide"),
    ("build-with-claude/structured-outputs", "Structured Outputs", "Guide"),
    ("build-with-claude/citations", "Citations", "Guide"),
    ("build-with-claude/streaming", "Streaming", "Guide"),
    ("build-with-claude/batch-processing", "Batch Processing", "Guide"),
    ("build-with-claude/pdf-support", "PDF Support", "Guide"),
    ("build-with-claude/search-results", "Search Results", "Guide"),
    ("build-with-claude/multilingual-support", "Multilingual Support", "Guide"),
    ("build-with-claude/embeddings", "Embeddings", "Guide"),
    ("build-with-claude/vision", "Vision", "Guide"),
    # Build with Claude - Context & Optimization
    ("build-with-claude/context-windows", "Context Windows", "Guide"),
    ("build-with-claude/compaction", "Compaction", "Guide"),
    ("build-with-claude/context-editing", "Context Editing", "Guide"),
    ("build-with-claude/prompt-caching", "Prompt Caching", "Guide"),
    ("build-with-claude/token-counting", "Token Counting", "Guide"),
    ("build-with-claude/files", "Files API", "Guide"),
    # Build with Claude - Integrations & Deployment
    ("build-with-claude/claude-on-amazon-bedrock", "Claude on Amazon Bedrock", "Guide"),
    ("build-with-claude/claude-in-microsoft-foundry", "Claude on Azure AI", "Guide"),
    ("build-with-claude/claude-on-vertex-ai", "Claude on Vertex AI", "Guide"),
    ("build-with-claude/administration-api", "Administration API", "Guide"),
    ("build-with-claude/data-residency", "Data Residency", "Guide"),
    ("build-with-claude/workspaces", "Workspaces", "Guide"),
    ("build-with-claude/usage-cost-api", "Usage & Cost API", "Guide"),
    ("build-with-claude/claude-code-analytics-api", "Claude Code Analytics API", "Guide"),
    ("build-with-claude/zero-data-retention", "Zero Data Retention", "Guide"),
    ("build-with-claude/skills-guide", "Skills Guide", "Guide"),
    # Prompt Engineering
    ("build-with-claude/prompt-engineering/overview", "Prompt Engineering Overview", "Guide"),
    ("build-with-claude/prompt-engineering/prompt-generator", "Prompt Generator", "Guide"),
    ("build-with-claude/prompt-engineering/prompt-templates-and-variables", "Prompt Templates", "Guide"),
    ("build-with-claude/prompt-engineering/prompt-improver", "Prompt Improver", "Guide"),
    ("build-with-claude/prompt-engineering/claude-prompting-best-practices", "Prompting Best Practices", "Guide"),
    ("build-with-claude/prompt-engineering/be-clear-and-direct", "Be Clear and Direct", "Guide"),
    ("build-with-claude/prompt-engineering/multishot-prompting", "Multishot Prompting", "Guide"),
    ("build-with-claude/prompt-engineering/chain-of-thought", "Chain of Thought", "Guide"),
    ("build-with-claude/prompt-engineering/use-xml-tags", "Use XML Tags", "Guide"),
    ("build-with-claude/prompt-engineering/system-prompts", "System Prompts", "Guide"),
    ("build-with-claude/prompt-engineering/chain-prompts", "Chain Prompts", "Guide"),
    ("build-with-claude/prompt-engineering/long-context-tips", "Long Context Tips", "Guide"),
    ("build-with-claude/prompt-engineering/extended-thinking-tips", "Extended Thinking Tips", "Guide"),
    # Agents and Tools - Tool Use
    ("agents-and-tools/tool-use/overview", "Tool Use Overview", "Guide"),
    ("agents-and-tools/tool-use/implement-tool-use", "Implement Tool Use", "Guide"),
    ("agents-and-tools/tool-use/web-search-tool", "Web Search Tool", "Guide"),
    ("agents-and-tools/tool-use/web-fetch-tool", "Web Fetch Tool", "Guide"),
    ("agents-and-tools/tool-use/code-execution-tool", "Code Execution Tool", "Guide"),
    ("agents-and-tools/tool-use/memory-tool", "Memory Tool", "Guide"),
    ("agents-and-tools/tool-use/bash-tool", "Bash Tool", "Guide"),
    ("agents-and-tools/tool-use/computer-use-tool", "Computer Use Tool", "Guide"),
    ("agents-and-tools/tool-use/text-editor-tool", "Text Editor Tool", "Guide"),
    ("agents-and-tools/tool-use/tool-search-tool", "Tool Search", "Guide"),
    ("agents-and-tools/tool-use/programmatic-tool-calling", "Programmatic Tool Calling", "Guide"),
    ("agents-and-tools/tool-use/fine-grained-tool-streaming", "Fine-Grained Tool Streaming", "Guide"),
    # Agents and Tools - Agent Skills
    ("agents-and-tools/agent-skills/overview", "Agent Skills Overview", "Guide"),
    ("agents-and-tools/agent-skills/quickstart", "Agent Skills Quickstart", "Guide"),
    ("agents-and-tools/agent-skills/best-practices", "Agent Skills Best Practices", "Guide"),
    ("agents-and-tools/agent-skills/enterprise", "Agent Skills Enterprise", "Guide"),
    # Agents and Tools - MCP
    ("agents-and-tools/mcp-connector", "MCP Connector", "Guide"),
    ("agents-and-tools/remote-mcp-servers", "Remote MCP Servers", "Guide"),
    # Agent SDK
    ("agent-sdk/overview", "Agent SDK Overview", "Guide"),
    ("agent-sdk/quickstart", "Agent SDK Quickstart", "Guide"),
    ("agent-sdk/typescript", "Agent SDK TypeScript", "Guide"),
    ("agent-sdk/typescript-v2-preview", "Agent SDK TypeScript v2 Preview", "Guide"),
    ("agent-sdk/python", "Agent SDK Python", "Guide"),
    ("agent-sdk/migration-guide", "Agent SDK Migration Guide", "Guide"),
    ("agent-sdk/streaming-vs-single-mode", "Streaming vs Single Mode", "Guide"),
    ("agent-sdk/streaming-output", "Streaming Output", "Guide"),
    ("agent-sdk/stop-reasons", "Stop Reasons", "Guide"),
    ("agent-sdk/permissions", "Agent SDK Permissions", "Guide"),
    ("agent-sdk/user-input", "User Input", "Guide"),
    ("agent-sdk/hooks", "Hooks", "Guide"),
    ("agent-sdk/sessions", "Sessions", "Guide"),
    ("agent-sdk/file-checkpointing", "File Checkpointing", "Guide"),
    ("agent-sdk/structured-outputs", "Agent SDK Structured Outputs", "Guide"),
    ("agent-sdk/hosting", "Hosting", "Guide"),
    ("agent-sdk/secure-deployment", "Secure Deployment", "Guide"),
    ("agent-sdk/modifying-system-prompts", "Modifying System Prompts", "Guide"),
    ("agent-sdk/mcp", "Agent SDK MCP", "Guide"),
    ("agent-sdk/custom-tools", "Custom Tools", "Guide"),
    ("agent-sdk/subagents", "Subagents", "Guide"),
    ("agent-sdk/slash-commands", "Slash Commands", "Guide"),
    ("agent-sdk/skills", "Agent SDK Skills", "Guide"),
    ("agent-sdk/cost-tracking", "Cost Tracking", "Guide"),
    ("agent-sdk/todo-tracking", "Todo Tracking", "Guide"),
    ("agent-sdk/plugins", "Plugins", "Guide"),
    # Test and Evaluate
    ("test-and-evaluate/define-success", "Define Success", "Guide"),
    ("test-and-evaluate/develop-tests", "Develop Tests", "Guide"),
    ("test-and-evaluate/eval-tool", "Eval Tool", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/reduce-latency", "Reduce Latency", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/reduce-hallucinations", "Reduce Hallucinations", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/increase-consistency", "Increase Consistency", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks", "Mitigate Jailbreaks", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/handle-streaming-refusals", "Handle Streaming Refusals", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/reduce-prompt-leak", "Reduce Prompt Leak", "Guide"),
    ("test-and-evaluate/strengthen-guardrails/keep-claude-in-character", "Keep Claude in Character", "Guide"),
    # API Reference
    ("api/overview", "API Overview", "Guide"),
    ("api/beta-headers", "Beta Headers", "Guide"),
    ("api/errors", "Errors", "Guide"),
    ("api/client-sdks", "Client SDKs", "Guide"),
    ("api/sdks/python", "Python SDK", "Guide"),
    ("api/sdks/typescript", "TypeScript SDK", "Guide"),
    ("api/sdks/java", "Java SDK", "Guide"),
    ("api/sdks/go", "Go SDK", "Guide"),
    ("api/sdks/ruby", "Ruby SDK", "Guide"),
    ("api/sdks/csharp", "C# SDK", "Guide"),
    ("api/sdks/php", "PHP SDK", "Guide"),
    ("api/rate-limits", "Rate Limits", "Guide"),
    ("api/service-tiers", "Service Tiers", "Guide"),
    ("api/versioning", "API Versioning", "Guide"),
    ("api/ip-addresses", "IP Addresses", "Guide"),
    ("api/supported-regions", "Supported Regions", "Guide"),
    ("api/openai-sdk", "OpenAI SDK Compatibility", "Guide"),
    # API Endpoints
    ("api/messages", "Messages API", "Endpoint"),
    ("api/messages-count-tokens", "Token Counting API", "Endpoint"),
    ("api/creating-message-batches", "Message Batches API", "Endpoint"),
    ("api/models-list", "Models API", "Endpoint"),
    ("api/files-create", "Files API", "Endpoint"),
    # Resources
    ("resources/overview", "Resources Overview", "Guide"),
    ("about-claude/glossary", "Glossary", "Guide"),
    ("release-notes/overview", "Release Notes", "Guide"),
    ("release-notes/api", "API Release Notes", "Guide"),
    ("release-notes/system-prompts", "System Prompts", "Guide"),
]


def download_docs():
    """Download documentation pages using wget."""
    print("Downloading Claude API documentation...")

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
                "--level=3",                # limit depth (deeper structure)
                "-q",                       # quiet
                "--wait=0.5",               # be polite
                "--random-wait",
                "-e", "robots=off",
                "--reject", "*.zip,*.tar.gz,*.whl,*.exe",
                "--reject-regex", r".*(/(de|es|fr|it|ja|ko|pt|zh)/).*",  # skip non-English
                "-I", "/docs/en/,/static/,/_next/",
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
    source = os.path.join(DOWNLOAD_DIR, "docs", "en")
    if not os.path.exists(source):
        source = os.path.join(DOWNLOAD_DIR, "docs")
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

    # Remove redirect and non-English pages
    for root, dirs, files in os.walk(DOCUMENTS_PATH):
        for f in files:
            if f.endswith(".html"):
                fpath = os.path.join(root, f)
                relpath = os.path.relpath(fpath, DOCUMENTS_PATH)
                if "@" in f or "?" in f:
                    print(f"Removing variant page: {relpath}")
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
    <string>claude-api</string>
    <key>CFBundleName</key>
    <string>Claude API</string>
    <key>DocSetPlatformFamily</key>
    <string>claude</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>home.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
    <key>isJavaScriptEnabled</key>
    <true/>
    <key>DashDocSetFallbackURL</key>
    <string>https://platform.claude.com/docs/en/</string>
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
[data-is-touch-wrapper],
#mintlify-sidebar, .mint-sidebar,
.mint-header, .mint-footer {
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
    print("=== Claude API Dash Docset Generator ===\n")

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
