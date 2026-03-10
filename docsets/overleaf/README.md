# Overleaf Dash Docset

A [Dash](https://kapeli.com/dash) docset for [Overleaf's LaTeX documentation](https://www.overleaf.com/learn), covering the full left-sidebar content of the Overleaf Learn portal.

## Coverage

The docset includes **90+ pages** from all sidebar sections:

| Section | Dash Entry Type |
|---|---|
| Introduction & LaTeX Basics | Guide |
| Mathematics | Guide, Command, Resource |
| Figures and Tables | Guide, Package |
| Document Structure | Guide |
| Formatting | Guide, Reference |
| References & Citations | Guide, Package, Resource |
| Fonts | Guide, Resource |
| Presentations | Package, Guide |
| Commands & Environments | Command, Type |
| Languages | Guide |
| Field-Specific Topics | Module, Package |
| Class Files | Guide, Resource |

## Prerequisites

- Python 3.10+
- [requests](https://pypi.org/project/requests/)
- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)
- [lxml](https://pypi.org/project/lxml/)

Install dependencies:

```bash
pip install requests beautifulsoup4 lxml
```

## Generating the Docset

Run the generation script from inside the `docsets/overleaf/` directory:

```bash
cd docsets/overleaf
python generate_docset.py
```

The script will:
1. Download each documentation page from `https://www.overleaf.com/learn` (with a short delay between requests to be polite).
2. Extract the article content, rewrite links to point back to the live site, and insert Dash table-of-contents anchors at every `<h2>` heading.
3. Build the SQLite search index (`docSet.dsidx`).
4. Write `Info.plist` and an auto-generated index page.
5. Package everything into **`Overleaf.tgz`**.

Runtime is roughly 2–3 minutes depending on network speed.

## Installing in Dash

After generation you can install the docset in one of two ways:

**Option A — Direct install:**
```bash
open Overleaf.docset
```

**Option B — Manual copy:**
```bash
cp -r Overleaf.docset ~/Library/Application\ Support/Dash/DocSets/
```

## Notes

- Pages that cannot be fetched (network error, 404, etc.) are replaced with a minimal placeholder that links to the live page.
- All internal links are rewritten to the live Overleaf site so that clicking through to related pages works even when the local copy doesn't contain that page.
- The docset does **not** bundle images; they are loaded from the live site (or omitted if unavailable offline). Set `isJavaScriptEnabled` to `true` in `Info.plist` if you want Overleaf's own MathJax rendering to be used.
