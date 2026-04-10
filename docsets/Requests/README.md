# Requests Docset

Docset made by Matt Cowger (@mcowger, github/mcowger) and Xavier Yang (@_ivaquero_, github/ivaquero)

## Building

The recommended way to build the docset is with the included
`make_docset.py` script.  It downloads the Requests documentation
directly from <https://requests.readthedocs.io/en/latest/>, hides
the left navigation sidebar and inline table-of-contents sections so
pages render cleanly in Dash, indexes all API symbols into the Dash
search database, and packages everything as `Requests.tgz`.

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
cd docsets/Requests
python make_docset.py
```

This produces `Requests.tgz` in the current directory.

#### Options

```
--icon-dir DIR   Directory containing icon.png (16×16) and icon@2x.png
                 (32×32). Defaults to the script's own directory.
```

### How it works

1. **Crawls** <https://requests.readthedocs.io/en/latest/> starting
   from the index, API reference, user guide, and community pages,
   following internal links to discover every HTML page.
2. **Injects CSS** into each page to hide the Alabaster theme's left
   navigation sidebar (`.sphinxsidebar`), any inline
   table-of-contents blocks (`.toctree-wrapper`, `div.topic.contents`),
   and the ReadTheDocs version-selector widget (`.rst-versions`).
   The main content area is expanded to fill the full page width.
3. **Downloads static assets** (CSS, JS, images, fonts) referenced by
   the HTML pages.
4. **Indexes** every symbol found in the API reference into the Dash
   SQLite search database.  Types (`Function`, `Class`, `Method`,
   `Attribute`, `Exception`) are read directly from the Sphinx
   `<dl class="py …">` markup — no heuristics needed.
5. **Packages** the docset as `Requests.tgz`.

Check [requests](https://github.com/psf/requests) for details.

Original authors of requests: Kenneth Reitz et al.
