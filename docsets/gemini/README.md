# Gemini API Dash Docset

Dash docset for the [Google Gemini API](https://ai.google.dev/gemini-api/docs/) documentation.

## Author

[venkatasg](https://github.com/venkatasg)

## Generation Instructions

### Prerequisites

- Python 3.8+
- `wget`
- `beautifulsoup4` Python package

Install Python dependencies:

```bash
pip install beautifulsoup4
```

On Ubuntu/Debian, install wget if not already present:

```bash
sudo apt-get install wget
```

On macOS:

```bash
brew install wget
```

### Generating the Docset

Run the generation script from this directory:

```bash
python3 generate_docset.py
```

The script will:

1. Download the Gemini API documentation from https://ai.google.dev/gemini-api/docs/ using `wget`
2. Create the docset folder structure (`Gemini_API.docset/`)
3. Copy and clean up downloaded HTML (removing localized/variant pages and redirects)
4. Generate the `Info.plist` configuration
5. Build the SQLite search index with Dash anchors for table of contents support
6. Inject CSS to hide navigation chrome for a cleaner reading experience in Dash
7. Package the docset into `Gemini_API.tgz`

### Installing

Open `Gemini_API.tgz` with Dash, or copy `Gemini_API.docset` to `~/Library/Application Support/Dash/DocSets/`.

## Notes

- The docset includes ~87 documentation pages covering models, capabilities, tools, guides, and API reference
- JavaScript is enabled in the docset (`isJavaScriptEnabled`) since some Google documentation pages use it for rendering
- Full-text search is enabled by default
- A fallback URL is configured so pages can be opened online if needed
