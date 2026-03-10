#!/usr/bin/env python3
"""
Overleaf Dash Docset Generator

Generates a Dash-compatible docset from Overleaf's LaTeX documentation at
https://www.overleaf.com/learn

Requirements:
    pip install requests beautifulsoup4 lxml

Usage:
    python generate_docset.py
"""

import os
import re
import shutil
import sqlite3
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DOCSET_NAME = "Overleaf"
DOCSET_DIR = f"{DOCSET_NAME}.docset"
DOCS_DIR = os.path.join(DOCSET_DIR, "Contents", "Resources", "Documents")
BASE_URL = "https://www.overleaf.com"
LEARN_BASE = "https://www.overleaf.com/learn/latex"

# Delay between HTTP requests to be polite
REQUEST_DELAY = 0.5  # seconds

# ---------------------------------------------------------------------------
# Pages to include, grouped by section.
# Each entry: (display_name, url_path, dash_type)
#
# Dash entry types used:
#   Guide    – tutorial / conceptual overview articles
#   Section  – major topic-grouping index pages
#   Package  – LaTeX packages (TikZ, Beamer, biblatex, …)
#   Command  – LaTeX commands / syntax reference
#   Module   – field-specific topics (chemistry, chess, …)
#   Type     – LaTeX environments
#   Resource – reference tables (Greek letters, font tables, …)
# ---------------------------------------------------------------------------

PAGES = [
    # ------------------------------------------------------------------
    # Introduction
    # ------------------------------------------------------------------
    ("Learn LaTeX in 30 Minutes",        "/learn/latex/Learn_LaTeX_in_30_minutes",                             "Guide"),

    # ------------------------------------------------------------------
    # LaTeX Basics
    # ------------------------------------------------------------------
    ("Creating a Document in LaTeX",     "/learn/latex/Creating_a_document_in_LaTeX",                          "Guide"),
    ("Paragraphs and New Lines",         "/learn/latex/Paragraphs_and_new_lines",                              "Guide"),
    ("Bold, Italics and Underlining",    "/learn/latex/Bold,_italics_and_underlining",                         "Guide"),
    ("Lists",                            "/learn/latex/Lists",                                                  "Guide"),
    ("Errors",                           "/learn/latex/Errors",                                                 "Guide"),

    # ------------------------------------------------------------------
    # Mathematics
    # ------------------------------------------------------------------
    ("Mathematical Expressions",         "/learn/latex/Mathematical_expressions",                              "Guide"),
    ("Subscripts and Superscripts",      "/learn/latex/Subscripts_and_superscripts",                          "Guide"),
    ("Brackets and Parentheses",         "/learn/latex/Brackets_and_Parentheses",                             "Guide"),
    ("Matrices",                         "/learn/latex/Matrices",                                              "Guide"),
    ("Fractions and Binomials",          "/learn/latex/Fractions_and_Binomials",                              "Guide"),
    ("Aligning Equations",               "/learn/latex/Aligning_equations_with_amsmath",                      "Guide"),
    ("Operators",                        "/learn/latex/Operators",                                             "Command"),
    ("Spacing in Math Mode",             "/learn/latex/Spacing_in_math_mode",                                 "Guide"),
    ("Integrals, Sums and Limits",       "/learn/latex/Integrals,_sums_and_limits",                           "Guide"),
    ("Display Style in Math Mode",       "/learn/latex/Display_style_in_math_mode",                           "Guide"),
    ("Greek Letters and Math Symbols",   "/learn/latex/List_of_Greek_letters_and_math_symbols",               "Resource"),
    ("Mathematical Fonts",               "/learn/latex/Mathematical_fonts",                                    "Guide"),

    # ------------------------------------------------------------------
    # Figures and Tables
    # ------------------------------------------------------------------
    ("Inserting Images",                 "/learn/latex/Inserting_Images",                                      "Guide"),
    ("Tables",                           "/learn/latex/Tables",                                                "Guide"),
    ("Positioning Images and Tables",    "/learn/latex/Positioning_images_and_tables",                        "Guide"),
    ("Lists of Tables and Figures",      "/learn/latex/Lists_of_tables_and_figures",                          "Guide"),
    ("Drawing Diagrams (Picture)",       "/learn/latex/Picture_environment",                                   "Guide"),
    ("TikZ Package",                     "/learn/latex/TikZ_package",                                         "Package"),

    # ------------------------------------------------------------------
    # Document Structure
    # ------------------------------------------------------------------
    ("Sections and Chapters",            "/learn/latex/Sections_and_chapters",                                 "Guide"),
    ("Table of Contents",                "/learn/latex/Table_of_contents",                                    "Guide"),
    ("Cross Referencing",                "/learn/latex/Cross_referencing_sections,_equations_and_floats",     "Guide"),
    ("Indices",                          "/learn/latex/Indices",                                               "Guide"),
    ("Glossaries",                       "/learn/latex/Glossaries",                                           "Guide"),
    ("Nomenclatures",                    "/learn/latex/Nomenclatures",                                        "Guide"),
    ("Management in a Large Project",    "/learn/latex/Management_in_a_large_project",                        "Guide"),
    ("Multi-file LaTeX Projects",        "/learn/latex/Multi-file_LaTeX_projects",                            "Guide"),
    ("Hyperlinks",                       "/learn/latex/Hyperlinks",                                           "Guide"),

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------
    ("Lengths in LaTeX",                 "/learn/latex/Lengths_in_LaTeX",                                      "Reference"),
    ("Headers and Footers",              "/learn/latex/Headers_and_footers",                                   "Guide"),
    ("Page Numbering",                   "/learn/latex/Page_numbering",                                       "Guide"),
    ("Paragraph Formatting",             "/learn/latex/Paragraph_formatting",                                  "Guide"),
    ("Line Breaks and Blank Spaces",     "/learn/latex/Line_breaks_and_blank_spaces",                          "Guide"),
    ("Text Alignment",                   "/learn/latex/Text_alignment",                                       "Guide"),
    ("Page Size and Margins",            "/learn/latex/Page_size_and_margins",                                 "Guide"),
    ("Single and Double Sided Docs",     "/learn/latex/Single_sided_and_double_sided_documents",               "Guide"),
    ("Multiple Columns",                 "/learn/latex/Multiple_columns",                                     "Guide"),
    ("Counters",                         "/learn/latex/Counters",                                              "Guide"),
    ("Code Listing",                     "/learn/latex/Code_listing",                                         "Guide"),
    ("Code Highlighting with minted",    "/learn/latex/Code_Highlighting_with_minted",                        "Package"),
    ("Using Colours in LaTeX",           "/learn/latex/Using_colours_in_LaTeX",                               "Guide"),
    ("Footnotes",                        "/learn/latex/Footnotes",                                            "Guide"),
    ("Margin Notes",                     "/learn/latex/Margin_notes",                                         "Guide"),

    # ------------------------------------------------------------------
    # References and Citations
    # ------------------------------------------------------------------
    ("Bibliography with BibTeX",         "/learn/latex/Bibliography_management_with_bibtex",                  "Guide"),
    ("Bibliography with natbib",         "/learn/latex/Bibliography_management_with_natbib",                  "Package"),
    ("Bibliography with biblatex",       "/learn/latex/Bibliography_management_with_biblatex",                "Package"),
    ("BibTeX Bibliography Styles",       "/learn/latex/Bibtex_bibliography_styles",                           "Resource"),
    ("Natbib Bibliography Styles",       "/learn/latex/Natbib_bibliography_styles",                           "Resource"),
    ("Natbib Citation Styles",           "/learn/latex/Natbib_citation_styles",                               "Resource"),
    ("Biblatex Bibliography Styles",     "/learn/latex/Biblatex_bibliography_styles",                         "Resource"),
    ("Biblatex Citation Styles",         "/learn/latex/Biblatex_citation_styles",                             "Resource"),

    # ------------------------------------------------------------------
    # Fonts
    # ------------------------------------------------------------------
    ("Font Sizes, Families, and Styles", "/learn/latex/Font_sizes,_families,_and_styles",                     "Resource"),
    ("Font Typefaces",                   "/learn/latex/Font_typefaces",                                       "Resource"),
    ("XeLaTeX",                          "/learn/latex/XeLaTeX",                                              "Guide"),

    # ------------------------------------------------------------------
    # Presentations
    # ------------------------------------------------------------------
    ("Beamer",                           "/learn/latex/Beamer",                                               "Package"),
    ("Powerdot",                         "/learn/latex/Powerdot",                                             "Package"),
    ("Posters",                          "/learn/latex/Posters",                                              "Guide"),

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    ("Commands",                         "/learn/latex/Commands",                                             "Command"),
    ("Environments",                     "/learn/latex/Environments",                                         "Type"),

    # ------------------------------------------------------------------
    # Languages
    # ------------------------------------------------------------------
    ("Multilingual: Polyglossia",        "/learn/latex/Multilingual_typesetting_on_Overleaf_using_polyglossia_and_fontspec", "Guide"),
    ("Multilingual: Babel",              "/learn/latex/Multilingual_typesetting_on_Overleaf_using_babel_and_fontspec",       "Guide"),
    ("International Language Support",   "/learn/latex/International_language_support",                       "Guide"),
    ("Typesetting Quotations",           "/learn/latex/Typesetting_quotations",                               "Guide"),
    ("Arabic",                           "/learn/latex/Arabic",                                               "Guide"),
    ("Chinese",                          "/learn/latex/Chinese",                                              "Guide"),
    ("French",                           "/learn/latex/French",                                               "Guide"),
    ("German",                           "/learn/latex/German",                                               "Guide"),
    ("Greek",                            "/learn/latex/Greek",                                                "Guide"),
    ("Italian",                          "/learn/latex/Italian",                                              "Guide"),
    ("Japanese",                         "/learn/latex/Japanese",                                             "Guide"),
    ("Korean",                           "/learn/latex/Korean",                                               "Guide"),
    ("Portuguese",                       "/learn/latex/Portuguese",                                           "Guide"),
    ("Russian",                          "/learn/latex/Russian",                                              "Guide"),
    ("Spanish",                          "/learn/latex/Spanish",                                              "Guide"),

    # ------------------------------------------------------------------
    # Field Specific
    # ------------------------------------------------------------------
    ("Theorems and Proofs",              "/learn/latex/Theorems_and_proofs",                                   "Module"),
    ("Chemistry Formulae",               "/learn/latex/Chemistry_formulae",                                   "Module"),
    ("Feynman Diagrams",                 "/learn/latex/Feynman_diagrams",                                     "Module"),
    ("Molecular Orbital Diagrams",       "/learn/latex/Molecular_orbital_diagrams",                           "Module"),
    ("Chess Notation",                   "/learn/latex/Chess_notation",                                       "Module"),
    ("Knitting Patterns",                "/learn/latex/Knitting_patterns",                                    "Module"),
    ("CircuiTikz Package",               "/learn/latex/CircuiTikz_package",                                   "Package"),
    ("Pgfplots Package",                 "/learn/latex/Pgfplots_package",                                     "Package"),
    ("Typesetting Exams",                "/learn/latex/Typesetting_exams_in_LaTeX",                           "Module"),
    ("Attribute Value Matrices",         "/learn/latex/Attribute_Value_Matrices",                             "Module"),

    # ------------------------------------------------------------------
    # Class Files
    # ------------------------------------------------------------------
    ("Understanding Packages and Class Files", "/learn/latex/Understanding_packages_and_class_files",         "Guide"),
    ("List of Packages and Class Files",       "/learn/latex/List_of_packages_and_class_files",              "Resource"),
    ("Writing Your Own Package",               "/learn/latex/Writing_your_own_package",                      "Guide"),
    ("Writing Your Own Class",                 "/learn/latex/Writing_your_own_class",                        "Guide"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (compatible; DashDocsetBot/1.0; "
        "+https://github.com/Kapeli/Dash-User-Contributions)"
    )
})


def url_path_to_filename(url_path: str) -> str:
    """Convert a URL path like /learn/latex/Foo_bar to docs/Foo_bar.html."""
    slug = url_path.rstrip("/").split("/")[-1]
    return os.path.join("docs", slug + ".html")


def fetch_page(url: str) -> BeautifulSoup | None:
    """Fetch a URL and return a BeautifulSoup object, or None on failure."""
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as exc:
        print(f"  WARNING: could not fetch {url}: {exc}")
        return None


def extract_article(soup: BeautifulSoup) -> BeautifulSoup | None:
    """
    Return a BeautifulSoup tag containing just the article body.
    Falls back to <body> if no article wrapper is found.
    """
    # Overleaf wraps the content in various containers; try common selectors
    for selector in (
        "article.page-content",
        "div.page-content",
        "div#content",
        "main",
        "article",
    ):
        node = soup.select_one(selector)
        if node:
            return node
    return soup.find("body")


def make_dash_anchor(entry_type: str, name: str) -> str:
    """Return an HTML anchor tag used by Dash for table-of-contents support."""
    encoded = urllib.parse.quote(name, safe="")
    return (
        f'<a name="//apple_ref/cpp/{entry_type}/{encoded}" '
        f'class="dashAnchor"></a>'
    )


def build_standalone_page(
    title: str,
    body_html: str,
    entry_type: str,
    online_url: str,
) -> str:
    """Wrap extracted body HTML in a minimal self-contained HTML page."""
    dash_anchor = make_dash_anchor(entry_type, title)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    /* ---- minimal readable stylesheet ---- */
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      line-height: 1.6;
      max-width: 860px;
      margin: 0 auto;
      padding: 1.5rem 2rem 4rem;
      color: #1a1a1a;
      background: #fff;
    }}
    h1, h2, h3, h4 {{ margin-top: 1.4em; }}
    pre, code {{
      background: #f5f5f5;
      border-radius: 4px;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 0.88em;
    }}
    pre {{ padding: 0.8em 1em; overflow-x: auto; }}
    code {{ padding: 0.15em 0.35em; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 1em 0;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 0.45em 0.75em;
      text-align: left;
    }}
    th {{ background: #f0f0f0; }}
    img {{ max-width: 100%; height: auto; }}
    a {{ color: #4f7fba; }}
    .online-link {{
      font-size: 0.85em;
      color: #666;
      margin-bottom: 1.5em;
    }}
  </style>
</head>
<body>
{dash_anchor}
<p class="online-link">
  Online version: <a href="{online_url}">{online_url}</a>
</p>
{body_html}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Core docset builder
# ---------------------------------------------------------------------------

def create_docset_skeleton() -> None:
    """Create the required directory structure for a Dash docset."""
    Path(DOCS_DIR).mkdir(parents=True, exist_ok=True)


def write_info_plist() -> None:
    """Write Contents/Info.plist."""
    plist_path = os.path.join(DOCSET_DIR, "Contents", "Info.plist")
    content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>overleaf</string>
  <key>CFBundleName</key>
  <string>Overleaf</string>
  <key>DocSetPlatformFamily</key>
  <string>overleaf</string>
  <key>isDashDocset</key>
  <true/>
  <key>dashIndexFilePath</key>
  <string>docs/Learn_LaTeX_in_30_minutes.html</string>
  <key>DashDocSetFallbackURL</key>
  <string>https://www.overleaf.com/learn/latex/</string>
  <key>DashDocSetFamily</key>
  <string>dashtoc</string>
  <key>isJavaScriptEnabled</key>
  <false/>
  <key>DashDocSetDefaultFTSEnabled</key>
  <true/>
</dict>
</plist>
"""
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print("Wrote Info.plist")


def create_database() -> sqlite3.Connection:
    """Create (or recreate) the SQLite search index and return a connection."""
    db_path = os.path.join(DOCSET_DIR, "Contents", "Resources", "docSet.dsidx")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE searchIndex("
        "  id INTEGER PRIMARY KEY,"
        "  name TEXT,"
        "  type TEXT,"
        "  path TEXT"
        ");"
    )
    conn.execute(
        "CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);"
    )
    conn.commit()
    print("Created docSet.dsidx")
    return conn


def add_index_entry(
    conn: sqlite3.Connection,
    name: str,
    entry_type: str,
    path: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?, ?, ?);",
        (name, entry_type, path),
    )


def process_page(
    conn: sqlite3.Connection,
    display_name: str,
    url_path: str,
    entry_type: str,
) -> None:
    """Download one documentation page, clean it up, and write it to disk."""
    full_url = BASE_URL + url_path
    local_path = url_path_to_filename(url_path)
    local_full = os.path.join(DOCS_DIR, os.path.basename(local_path))

    print(f"  Fetching: {display_name}  ({full_url})")
    time.sleep(REQUEST_DELAY)

    soup = fetch_page(full_url)
    if soup is None:
        # Write a minimal placeholder so the docset remains consistent
        placeholder = build_standalone_page(
            display_name,
            f"<p>Could not retrieve this page. "
            f'<a href="{full_url}">View online</a>.</p>',
            entry_type,
            full_url,
        )
        with open(local_full, "w", encoding="utf-8") as fh:
            fh.write(placeholder)
        add_index_entry(conn, display_name, entry_type, local_path)
        return

    # Pull the title from the page if available
    page_title_tag = soup.find("h1")
    page_title = page_title_tag.get_text(strip=True) if page_title_tag else display_name

    # Extract article content
    article = extract_article(soup)
    body_html = str(article) if article else "<p>No content extracted.</p>"

    # Rewrite relative links to absolute so they work offline via fallback
    body_soup = BeautifulSoup(body_html, "lxml")
    for tag in body_soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("/"):
            tag["href"] = BASE_URL + href
        elif href.startswith(".."):
            tag["href"] = urllib.parse.urljoin(full_url, href)

    # Remove images that point to external resources (keep page lightweight)
    for img in body_soup.find_all("img", src=True):
        src = img["src"]
        if not src.startswith("data:"):
            img["src"] = BASE_URL + src if src.startswith("/") else src

    # Insert Dash section anchors for every <h2> heading found on the page
    for heading in body_soup.find_all("h2"):
        heading_text = heading.get_text(strip=True)
        if heading_text:
            anchor_tag = BeautifulSoup(
                make_dash_anchor("Section", heading_text), "lxml"
            ).find("a")
            heading.insert_before(anchor_tag)
            # Also add to the search index as a Section entry
            anchor_path = local_path + "#" + urllib.parse.quote(heading_text, safe="")
            add_index_entry(conn, heading_text, "Section", anchor_path)

    cleaned_body = str(body_soup.find("body") or body_soup)

    html = build_standalone_page(display_name, cleaned_body, entry_type, full_url)
    with open(local_full, "w", encoding="utf-8") as fh:
        fh.write(html)

    add_index_entry(conn, display_name, entry_type, local_path)


def build_index_page(conn: sqlite3.Connection) -> None:
    """
    Generate a simple HTML index page listing all docset entries,
    grouped by entry type.
    """
    # Fetch all entries sorted by type then name
    rows = conn.execute(
        "SELECT name, type, path FROM searchIndex "
        "WHERE path NOT LIKE '%#%' "
        "ORDER BY type, name;"
    ).fetchall()

    # Group
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, etype, path in rows:
        groups.setdefault(etype, []).append((name, path))

    sections_html = ""
    for etype in sorted(groups):
        items = groups[etype]
        li_items = "\n".join(
            f'    <li><a href="{p}">{n}</a></li>' for n, p in items
        )
        sections_html += f"<h2>{etype}</h2>\n<ul>\n{li_items}\n</ul>\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Overleaf Documentation</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      max-width: 860px; margin: 0 auto; padding: 2rem;
      color: #1a1a1a;
    }}
    h1 {{ border-bottom: 2px solid #4f8a38; padding-bottom: 0.4em; }}
    h2 {{ color: #4f8a38; margin-top: 1.8em; }}
    ul {{ columns: 2; column-gap: 2em; }}
    li {{ break-inside: avoid; margin-bottom: 0.3em; }}
    a {{ color: #4f7fba; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
<h1>Overleaf LaTeX Documentation</h1>
<p>
  This docset covers the Overleaf / LaTeX learning guides available at
  <a href="https://www.overleaf.com/learn">www.overleaf.com/learn</a>.
</p>
{sections_html}
</body>
</html>
"""
    index_path = os.path.join(DOCS_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("Wrote docs/index.html")


def package_docset() -> None:
    """Create a .tgz archive of the finished docset."""
    import tarfile

    archive_name = f"{DOCSET_NAME}.tgz"
    print(f"Packaging {archive_name} …")
    with tarfile.open(archive_name, "w:gz") as tar:
        tar.add(DOCSET_DIR, arcname=DOCSET_DIR)
    print(f"Done — archive written to {archive_name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"=== Building {DOCSET_NAME} Dash Docset ===\n")

    # Clean up any previous build
    if os.path.exists(DOCSET_DIR):
        shutil.rmtree(DOCSET_DIR)
        print(f"Removed previous {DOCSET_DIR}/")

    create_docset_skeleton()
    write_info_plist()
    conn = create_database()

    print(f"\nDownloading {len(PAGES)} documentation pages …\n")
    for display_name, url_path, entry_type in PAGES:
        process_page(conn, display_name, url_path, entry_type)

    conn.commit()

    build_index_page(conn)
    conn.close()

    package_docset()

    print("\n=== Done ===")
    print(f"Docset:  ./{DOCSET_DIR}")
    print(f"Archive: ./{DOCSET_NAME}.tgz")
    print(
        "\nTo install: open Overleaf.tgz in Dash, or copy Overleaf.docset "
        "to ~/Library/Application Support/Dash/DocSets/"
    )


if __name__ == "__main__":
    main()
