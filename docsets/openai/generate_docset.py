#!/usr/bin/env python3
"""Generate a Dash docset for the OpenAI API Reference."""

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
BASE_URL = "https://developers.openai.com/api/reference/"
ARCHIVE_NAME = "OpenAI_API.tgz"

# API Reference pages only, organized by resource.
# Each entry is (relative_path, display_name, entry_type).
# Entry types:
#   Guide     - overview/introductory pages
#   Method    - individual API endpoint (create, retrieve, delete, etc.)
#   Resource  - resource grouping pages
#   Event     - streaming events / webhooks
#   Section   - sub-headings (auto-generated)
DOC_PAGES = [
    # Overview
    ("overview", "API Reference Overview", "Guide"),
    # Responses
    ("responses/overview", "Responses Overview", "Resource"),
    ("resources/responses/methods/create", "Create a response", "Method"),
    ("resources/responses/methods/retrieve", "Retrieve a response", "Method"),
    ("resources/responses/methods/delete", "Delete a response", "Method"),
    ("resources/responses/subresources/input_items/methods/list", "List input items", "Method"),
    ("resources/responses/subresources/input_tokens/methods/count", "Count input tokens", "Method"),
    ("resources/responses/methods/cancel", "Cancel a response", "Method"),
    ("resources/responses/methods/compact", "Compact a response", "Method"),
    ("resources/responses/streaming-events", "Response streaming events", "Event"),
    # Conversations
    ("resources/conversations/methods/create", "Create a conversation", "Method"),
    ("resources/conversations/methods/retrieve", "Retrieve a conversation", "Method"),
    ("resources/conversations/methods/update", "Update a conversation", "Method"),
    ("resources/conversations/methods/delete", "Delete a conversation", "Method"),
    ("resources/conversations/subresources/items/methods/create", "Create conversation item", "Method"),
    ("resources/conversations/subresources/items/methods/retrieve", "Retrieve conversation item", "Method"),
    ("resources/conversations/subresources/items/methods/delete", "Delete conversation item", "Method"),
    ("resources/conversations/subresources/items/methods/list", "List conversation items", "Method"),
    # Webhooks
    ("resources/webhooks", "Webhooks", "Event"),
    # Chat Completions
    ("chat-completions/overview", "Chat Completions Overview", "Resource"),
    ("resources/chat/subresources/completions/methods/create", "Create chat completion", "Method"),
    ("resources/chat/subresources/completions/methods/retrieve", "Retrieve chat completion", "Method"),
    ("resources/chat/subresources/completions/methods/update", "Update chat completion", "Method"),
    ("resources/chat/subresources/completions/methods/delete", "Delete chat completion", "Method"),
    ("resources/chat/subresources/completions/methods/list", "List chat completions", "Method"),
    ("resources/chat/subresources/completions/subresources/messages/methods/list", "List chat messages", "Method"),
    ("resources/chat/subresources/completions/streaming-events", "Chat streaming events", "Event"),
    # Audio
    ("resources/audio/subresources/transcriptions/methods/create", "Create transcription", "Method"),
    ("resources/audio/subresources/translations/methods/create", "Create translation", "Method"),
    ("resources/audio/subresources/speech/methods/create", "Create speech", "Method"),
    ("resources/audio/subresources/voices/methods/create", "Create voice", "Method"),
    # Voice Consents
    ("resources/audio/subresources/voice_consents/methods/create", "Create voice consent", "Method"),
    ("resources/audio/subresources/voice_consents/methods/retrieve", "Retrieve voice consent", "Method"),
    ("resources/audio/subresources/voice_consents/methods/update", "Update voice consent", "Method"),
    ("resources/audio/subresources/voice_consents/methods/delete", "Delete voice consent", "Method"),
    ("resources/audio/subresources/voice_consents/methods/list", "List voice consents", "Method"),
    # Videos
    ("resources/videos/methods/create", "Create video", "Method"),
    ("resources/videos/methods/retrieve", "Retrieve video", "Method"),
    ("resources/videos/methods/delete", "Delete video", "Method"),
    ("resources/videos/methods/list", "List videos", "Method"),
    ("resources/videos/methods/download_content", "Download video content", "Method"),
    ("resources/videos/methods/remix", "Remix video", "Method"),
    # Images
    ("resources/images/methods/generate", "Generate image", "Method"),
    ("resources/images/methods/edit", "Edit image", "Method"),
    ("resources/images/methods/create_variation", "Create image variation", "Method"),
    ("resources/images/generation-streaming-events", "Image generation streaming events", "Event"),
    ("resources/images/edit-streaming-events", "Image edit streaming events", "Event"),
    # Embeddings
    ("resources/embeddings/methods/create", "Create embedding", "Method"),
    # Evals
    ("resources/evals/methods/create", "Create eval", "Method"),
    ("resources/evals/methods/retrieve", "Retrieve eval", "Method"),
    ("resources/evals/methods/update", "Update eval", "Method"),
    ("resources/evals/methods/delete", "Delete eval", "Method"),
    ("resources/evals/methods/list", "List evals", "Method"),
    ("resources/evals/subresources/runs/methods/create", "Create eval run", "Method"),
    ("resources/evals/subresources/runs/methods/retrieve", "Retrieve eval run", "Method"),
    ("resources/evals/subresources/runs/methods/delete", "Delete eval run", "Method"),
    ("resources/evals/subresources/runs/methods/list", "List eval runs", "Method"),
    ("resources/evals/subresources/runs/methods/cancel", "Cancel eval run", "Method"),
    ("resources/evals/subresources/runs/subresources/output_items/methods/retrieve", "Retrieve eval output item", "Method"),
    ("resources/evals/subresources/runs/subresources/output_items/methods/list", "List eval output items", "Method"),
    # Fine Tuning
    ("resources/fine_tuning/subresources/jobs/methods/create", "Create fine-tuning job", "Method"),
    ("resources/fine_tuning/subresources/jobs/methods/retrieve", "Retrieve fine-tuning job", "Method"),
    ("resources/fine_tuning/subresources/jobs/methods/list", "List fine-tuning jobs", "Method"),
    ("resources/fine_tuning/subresources/jobs/methods/list_events", "List fine-tuning events", "Method"),
    ("resources/fine_tuning/subresources/jobs/methods/cancel", "Cancel fine-tuning job", "Method"),
    ("resources/fine_tuning/subresources/jobs/methods/pause", "Pause fine-tuning job", "Method"),
    ("resources/fine_tuning/subresources/jobs/methods/resume", "Resume fine-tuning job", "Method"),
    ("resources/fine_tuning/subresources/jobs/subresources/checkpoints/methods/list", "List fine-tuning checkpoints", "Method"),
    ("resources/fine_tuning/subresources/checkpoints/subresources/permissions/methods/create", "Create checkpoint permission", "Method"),
    ("resources/fine_tuning/subresources/checkpoints/subresources/permissions/methods/retrieve", "Retrieve checkpoint permission", "Method"),
    ("resources/fine_tuning/subresources/checkpoints/subresources/permissions/methods/delete", "Delete checkpoint permission", "Method"),
    ("resources/fine_tuning/subresources/alpha/subresources/graders/methods/run", "Run grader", "Method"),
    ("resources/fine_tuning/subresources/alpha/subresources/graders/methods/validate", "Validate grader", "Method"),
    # Batches
    ("resources/batches/methods/create", "Create batch", "Method"),
    ("resources/batches/methods/retrieve", "Retrieve batch", "Method"),
    ("resources/batches/methods/list", "List batches", "Method"),
    ("resources/batches/methods/cancel", "Cancel batch", "Method"),
    # Files
    ("resources/files/methods/list", "List files", "Method"),
    ("resources/files/methods/create", "Create file", "Method"),
    ("resources/files/methods/retrieve", "Retrieve file", "Method"),
    ("resources/files/methods/delete", "Delete file", "Method"),
    ("resources/files/methods/content", "Retrieve file content", "Method"),
    # Uploads
    ("resources/uploads/methods/create", "Create upload", "Method"),
    ("resources/uploads/methods/cancel", "Cancel upload", "Method"),
    ("resources/uploads/methods/complete", "Complete upload", "Method"),
    ("resources/uploads/subresources/parts/methods/create", "Create upload part", "Method"),
    # Models
    ("resources/models/methods/retrieve", "Retrieve model", "Method"),
    ("resources/models/methods/delete", "Delete model", "Method"),
    ("resources/models/methods/list", "List models", "Method"),
    # Moderations
    ("resources/moderations/methods/create", "Create moderation", "Method"),
    # Vector Stores
    ("resources/vector_stores/methods/create", "Create vector store", "Method"),
    ("resources/vector_stores/methods/retrieve", "Retrieve vector store", "Method"),
    ("resources/vector_stores/methods/update", "Update vector store", "Method"),
    ("resources/vector_stores/methods/delete", "Delete vector store", "Method"),
    ("resources/vector_stores/methods/list", "List vector stores", "Method"),
    ("resources/vector_stores/methods/search", "Search vector store", "Method"),
    ("resources/vector_stores/subresources/files/methods/list", "List vector store files", "Method"),
    ("resources/vector_stores/subresources/files/methods/create", "Create vector store file", "Method"),
    ("resources/vector_stores/subresources/files/methods/retrieve", "Retrieve vector store file", "Method"),
    ("resources/vector_stores/subresources/files/methods/update", "Update vector store file", "Method"),
    ("resources/vector_stores/subresources/files/methods/delete", "Delete vector store file", "Method"),
    ("resources/vector_stores/subresources/files/methods/content", "Retrieve vector store file content", "Method"),
    ("resources/vector_stores/subresources/file_batches/methods/create", "Create vector store file batch", "Method"),
    ("resources/vector_stores/subresources/file_batches/methods/retrieve", "Retrieve vector store file batch", "Method"),
    ("resources/vector_stores/subresources/file_batches/methods/list_files", "List vector store batch files", "Method"),
    ("resources/vector_stores/subresources/file_batches/methods/cancel", "Cancel vector store file batch", "Method"),
    # ChatKit
    ("resources/beta/subresources/chatkit/subresources/sessions/methods/create", "Create ChatKit session", "Method"),
    ("resources/beta/subresources/chatkit/subresources/sessions/methods/cancel", "Cancel ChatKit session", "Method"),
    ("resources/beta/subresources/chatkit/subresources/threads/methods/retrieve", "Retrieve ChatKit thread", "Method"),
    ("resources/beta/subresources/chatkit/subresources/threads/methods/delete", "Delete ChatKit thread", "Method"),
    ("resources/beta/subresources/chatkit/subresources/threads/methods/list_items", "List ChatKit thread items", "Method"),
    ("resources/beta/subresources/chatkit/subresources/threads/methods/list", "List ChatKit threads", "Method"),
    # Containers
    ("resources/containers/methods/create", "Create container", "Method"),
    ("resources/containers/methods/retrieve", "Retrieve container", "Method"),
    ("resources/containers/methods/delete", "Delete container", "Method"),
    ("resources/containers/methods/list", "List containers", "Method"),
    ("resources/containers/subresources/files/methods/list", "List container files", "Method"),
    ("resources/containers/subresources/files/methods/create", "Create container file", "Method"),
    ("resources/containers/subresources/files/methods/retrieve", "Retrieve container file", "Method"),
    ("resources/containers/subresources/files/methods/delete", "Delete container file", "Method"),
    ("resources/containers/subresources/files/subresources/content/methods/retrieve", "Retrieve container file content", "Method"),
    # Skills
    ("resources/skills/methods/create", "Create skill", "Method"),
    ("resources/skills/methods/retrieve", "Retrieve skill", "Method"),
    ("resources/skills/subresources/content/methods/retrieve", "Retrieve skill content", "Method"),
    ("resources/skills/methods/update", "Update skill", "Method"),
    ("resources/skills/methods/delete", "Delete skill", "Method"),
    ("resources/skills/methods/list", "List skills", "Method"),
    ("resources/skills/subresources/versions/methods/create", "Create skill version", "Method"),
    ("resources/skills/subresources/versions/methods/retrieve", "Retrieve skill version", "Method"),
    ("resources/skills/subresources/versions/subresources/content/methods/retrieve", "Retrieve skill version content", "Method"),
    ("resources/skills/subresources/versions/methods/delete", "Delete skill version", "Method"),
    ("resources/skills/subresources/versions/methods/list", "List skill versions", "Method"),
    # Realtime
    ("resources/realtime/subresources/calls/methods/accept", "Accept realtime call", "Method"),
    ("resources/realtime/subresources/calls/methods/hangup", "Hangup realtime call", "Method"),
    ("resources/realtime/subresources/calls/methods/refer", "Refer realtime call", "Method"),
    ("resources/realtime/subresources/calls/methods/reject", "Reject realtime call", "Method"),
    ("resources/realtime/subresources/client_secrets/methods/create", "Create client secret", "Method"),
    ("resources/realtime/client-events", "Realtime client events", "Event"),
    ("resources/realtime/server-events", "Realtime server events", "Event"),
    # Administration
    ("administration/overview", "Administration Overview", "Resource"),
    ("resources/organization/subresources/audit_logs/methods/get_costs", "Get costs", "Method"),
    ("resources/organization/subresources/audit_logs/methods/list", "List audit logs", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/admin_api_keys/methods/create", "Create admin API key", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/admin_api_keys/methods/retrieve", "Retrieve admin API key", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/admin_api_keys/methods/delete", "Delete admin API key", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/admin_api_keys/methods/list", "List admin API keys", "Method"),
    # Usage
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_audio_speeches", "Get audio speeches usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_audio_transcriptions", "Get audio transcriptions usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_code_interpreter_sessions", "Get code interpreter usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_completions", "Get completions usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_embeddings", "Get embeddings usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_images", "Get images usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_moderations", "Get moderations usage", "Method"),
    ("resources/organization/subresources/audit_logs/subresources/usage/methods/get_vector_stores", "Get vector stores usage", "Method"),
    # Invites
    ("resources/organization/subresources/invites/methods/create", "Create invite", "Method"),
    ("resources/organization/subresources/invites/methods/retrieve", "Retrieve invite", "Method"),
    ("resources/organization/subresources/invites/methods/delete", "Delete invite", "Method"),
    ("resources/organization/subresources/invites/methods/list", "List invites", "Method"),
    # Users
    ("resources/organization/subresources/users/methods/retrieve", "Retrieve user", "Method"),
    ("resources/organization/subresources/users/methods/update", "Update user", "Method"),
    ("resources/organization/subresources/users/methods/delete", "Delete user", "Method"),
    ("resources/organization/subresources/users/methods/list", "List users", "Method"),
    # Projects
    ("resources/organization/subresources/projects/methods/create", "Create project", "Method"),
    ("resources/organization/subresources/projects/methods/retrieve", "Retrieve project", "Method"),
    ("resources/organization/subresources/projects/methods/update", "Update project", "Method"),
    ("resources/organization/subresources/projects/methods/list", "List projects", "Method"),
    ("resources/organization/subresources/projects/methods/archive", "Archive project", "Method"),
    # Legacy - Completions
    ("resources/completions/methods/create", "Create completion (legacy)", "Method"),
    # Legacy - Realtime Beta
    ("realtime-beta/overview", "Realtime Beta Overview (legacy)", "Resource"),
    ("resources/realtime/subresources/sessions/methods/create", "Create realtime session (legacy)", "Method"),
    ("resources/realtime/subresources/transcription_sessions/methods/create", "Create transcription session (legacy)", "Method"),
    # Legacy - Assistants
    ("resources/beta/subresources/threads/methods/create", "Create thread (legacy)", "Method"),
    ("resources/beta/subresources/threads/methods/create_and_run", "Create and run thread (legacy)", "Method"),
    ("resources/beta/subresources/threads/methods/retrieve", "Retrieve thread (legacy)", "Method"),
    ("resources/beta/subresources/threads/methods/update", "Update thread (legacy)", "Method"),
    ("resources/beta/subresources/threads/methods/delete", "Delete thread (legacy)", "Method"),
    ("resources/beta/subresources/assistants/methods/create", "Create assistant (legacy)", "Method"),
    ("resources/beta/subresources/assistants/methods/retrieve", "Retrieve assistant (legacy)", "Method"),
    ("resources/beta/subresources/assistants/methods/update", "Update assistant (legacy)", "Method"),
    ("resources/beta/subresources/assistants/methods/delete", "Delete assistant (legacy)", "Method"),
    ("resources/beta/subresources/assistants/methods/list", "List assistants (legacy)", "Method"),
    ("resources/beta/subresources/assistants/streaming-events", "Assistants streaming events (legacy)", "Event"),
]


def download_docs():
    """Download API reference pages using wget."""
    print("Downloading OpenAI API reference...")

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
                "--level=5",                # deep nesting in resource paths
                "-q",                       # quiet
                "--wait=0.5",
                "--random-wait",
                "-e", "robots=off",
                "--reject", "*.zip,*.tar.gz,*.whl,*.exe",
                "--reject-regex", r".*[@?].*=.*",
                "-I", "/api/reference/,/static/,/_next/",
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
    source = os.path.join(DOWNLOAD_DIR, "api", "reference")
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

    # Remove redirect and variant pages
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
    <string>openai-api</string>
    <key>CFBundleName</key>
    <string>OpenAI API</string>
    <key>DocSetPlatformFamily</key>
    <string>openai</string>
    <key>isDashDocset</key>
    <true/>
    <key>dashIndexFilePath</key>
    <string>overview.html</string>
    <key>DashDocSetFamily</key>
    <string>dashtoc</string>
    <key>isJavaScriptEnabled</key>
    <true/>
    <key>DashDocSetFallbackURL</key>
    <string>https://developers.openai.com/api/reference/</string>
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
                                   "path param", "header", "body param",
                                   "properties", "arguments"]):
        return "Parameter"

    # Response/return type headings
    if any(kw in lower for kw in ["response", "returns", "return type",
                                   "the .* object"]):
        return "Value"

    # Object/type definitions
    if any(kw in lower for kw in ["object", "schema", "enum", "type"]):
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

    # Fallback classification
    if "/methods/" in normalized:
        return None, "Method"
    if "streaming-events" in normalized or "client-events" in normalized or "server-events" in normalized:
        return None, "Event"
    if "/overview" in normalized:
        return None, "Resource"

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

            # Index headings within the page
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
header,
nav,
[role="navigation"],
.sidebar,
.top-nav,
.site-header,
.site-footer,
footer,
.search-form,
.search-bar,
input[type="search"],
.breadcrumb,
.breadcrumbs,
.feedback-widget,
.page-rating,
.cookie-notification,
.cookie-banner,
button[aria-label="Search"],
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
    print("=== OpenAI API Reference Dash Docset Generator ===\n")

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
