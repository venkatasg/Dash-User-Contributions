# Seaborn docset

## Authors

- [Paulo S. Costa](https://github.com/paw-lu)
- [Xavier Yang](https://github.com/ivaquero)

## Building

The recommended way to build the docset is with the included
`make_docset.py` script.  It downloads the seaborn documentation
directly from <https://seaborn.pydata.org/>, strips the header
navigation bar and both sidebars so pages render cleanly in Dash,
indexes all API symbols into the Dash search database, and packages
everything as `seaborn.tgz`.

### Requirements

- Python 3.9+
- [requests](https://pypi.org/project/requests/)
- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)

Install the dependencies with:

```bash
pip install requests beautifulsoup4
```

### Build directions

```bash
cd docsets/Seaborn
python make_docset.py
```

This produces `seaborn.tgz` in the current directory.

#### Options

```
--icon-dir DIR   Directory containing icon.png (16×16) and icon@2x.png
                 (32×32). Defaults to the script's own directory.
```

### How it works

1. **Crawls** <https://seaborn.pydata.org/> starting from the index,
   API reference, tutorials, and a few other key pages, following
   internal links to discover every HTML page.
2. **Injects CSS** into each page to hide the header navbar
   (`nav.bd-header`), primary sidebar (`.bd-sidebar-primary`), and
   secondary sidebar / TOC (`.bd-sidebar-secondary`) so they do not
   appear inside Dash.
3. **Downloads static assets** (CSS, JS, images, fonts) referenced by
   the HTML pages.
4. **Indexes** every symbol found in `api.html` into the Dash SQLite
   search database, assigning appropriate types (`Function`, `Class`,
   or `Method`).
5. **Packages** the docset as `seaborn.tgz`.
