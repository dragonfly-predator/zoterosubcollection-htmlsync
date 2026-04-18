#!/usr/bin/env python3
"""
Fetches a Zotero subcollection via the Web API and generates index.html with MLA citations.

Required environment variables:
  ZOTERO_API_KEY      — your Zotero API key
  ZOTERO_USER_ID      — your Zotero user ID (numeric)
  ZOTERO_COLLECTION   — the collection key (8-character string, e.g. "AB12CD34")

Optional:
  ZOTERO_LIBRARY_TYPE — "user" (default) or "group"
  OUTPUT_FILE         — output path (default: "index.html")
  PAGE_TITLE          — title shown on the page (default: "Zotero Library")
"""

import os
import re
import sys
import json
import string
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from html import escape

# ── Configuration ────────────────────────────────────────────────────────────

API_KEY       = os.environ.get("ZOTERO_API_KEY", "")
USER_ID       = os.environ.get("ZOTERO_USER_ID", "")
COLLECTION    = os.environ.get("ZOTERO_COLLECTION", "")
LIBRARY_TYPE  = os.environ.get("ZOTERO_LIBRARY_TYPE", "user")
OUTPUT_FILE   = os.environ.get("OUTPUT_FILE", "index.html")
PAGE_TITLE    = os.environ.get("PAGE_TITLE", "")

BASE_URL = f"https://api.zotero.org/{LIBRARY_TYPE}s/{USER_ID}"

# ── Zotero API helpers ────────────────────────────────────────────────────────

def zotero_get(path, params=None, retries=4, backoff=5):
    """GET from the Zotero API, returns parsed JSON. Retries on 5xx/timeout."""
    import time
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Zotero-API-Key": API_KEY,
        "Zotero-API-Version": "3",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                print(f"  HTTP {e.code} — retrying in {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            else:
                raise
        except OSError:
            if attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                print(f"  Timeout — retrying in {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            else:
                raise

def fetch_all_items(collection_key):
    """Fetch all items in a collection, handling pagination."""
    EXCLUDE_TYPES = {"attachment", "note"}
    items = []
    start = 0
    limit = 100
    while True:
        batch = zotero_get(f"/collections/{collection_key}/items/top", {
            "limit": limit,
            "start": start,
        })
        if not batch:
            break
        items.extend(
            item for item in batch
            if item.get("data", {}).get("itemType") not in EXCLUDE_TYPES
        )
        if len(batch) < limit:
            break
        start += limit
    return items

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_year(date_str):
    """Extract a 4-digit year from any date string (e.g. 'July 2024', '2024-07-01')."""
    if not date_str:
        return ""
    m = re.search(r'\b(1[5-9]\d\d|20\d\d)\b', date_str)
    return m.group(1) if m else ""

# ── MLA formatting ────────────────────────────────────────────────────────────

def format_author_mla(creator):
    if "lastName" in creator and "firstName" in creator:
        return f"{creator['lastName']}, {creator['firstName']}"
    return creator.get("name", "")

def format_author_normal(creator):
    if "firstName" in creator and "lastName" in creator:
        return f"{creator['firstName']} {creator['lastName']}".strip()
    return creator.get("name", "")

def format_authors_mla(creators):
    """MLA 9th-edition author list."""
    authors = [c for c in creators if c.get("creatorType") == "author"]
    if not authors:
        authors = creators
    if not authors:
        return ""
    if len(authors) == 1:
        return format_author_mla(authors[0])
    if len(authors) <= 3:
        parts = [format_author_mla(authors[0])]
        for a in authors[1:-1]:
            parts.append(format_author_normal(a))
        parts_str = ", ".join(parts)
        return f"{parts_str}, and {format_author_normal(authors[-1])}"
    return f"{format_author_mla(authors[0])}, et al."

def format_mla(data):
    """
    Build an MLA 9th-edition citation string.
    Returns plain text — *italics* markers and URL placeholders resolved later.
    """
    item_type  = data.get("itemType", "")
    title      = data.get("title", "Untitled")
    creators   = data.get("creators", [])
    year       = extract_year(data.get("date") or "")
    url        = data.get("url", "")
    doi        = data.get("DOI", "")
    publisher  = data.get("publisher", "") or data.get("institution", "")
    journal    = data.get("publicationTitle", "") or data.get("journalAbbreviation", "")
    volume     = data.get("volume", "")
    issue      = data.get("issue", "")
    pages      = data.get("pages", "")
    edition    = data.get("edition", "")
    website    = data.get("websiteTitle", "") or data.get("blogTitle", "")

    authors_str = format_authors_mla(creators)
    parts = []

    # Authors — avoid double period when name ends with an abbreviation
    if authors_str:
        parts.append(authors_str if authors_str.endswith(".") else authors_str + ".")

    # Title (webpage/blogPost use website title as container; individual page title omitted)
    if item_type in ("journalArticle", "magazineArticle", "newspaperArticle",
                     "bookSection", "conferencePaper"):
        end = "" if title.rstrip() and title.rstrip()[-1] in ".?!" else "."
        parts.append(f'"{title}{end}"')
    elif item_type in ("webpage", "blogPost"):
        pass
    else:
        parts.append(f"*{title}*.")

    # Edition (books, reports, theses)
    if edition and item_type in ("book", "report", "thesis"):
        ed_str = edition if re.search(r'\bed\b', edition, re.I) else f"{edition} ed."
        parts.append(ed_str + ",")

    # Container / source
    if item_type == "journalArticle":
        if journal:
            vol_issue = ""
            if volume:
                vol_issue += f"vol. {volume}"
            if issue:
                vol_issue += (", " if vol_issue else "") + f"no. {issue}"
            parts.append(f"*{journal}*,")
            if vol_issue:
                parts.append(vol_issue + ",")
            if year:
                parts.append(year + ",")
            if pages:
                parts.append(f"pp. {pages}.")
            else:
                if parts and parts[-1].endswith(","):
                    parts[-1] = parts[-1][:-1] + "."
        else:
            # No journal title — still emit year
            if year:
                parts.append(year + ".")

    elif item_type == "bookSection":
        book_title = data.get("bookTitle", "")
        editors = [c for c in creators if c.get("creatorType") == "editor"]
        if book_title:
            parts.append(f"*{book_title}*,")
        if editors:
            ed_names = ", ".join(
                f"{e.get('firstName','')} {e.get('lastName','')}".strip()
                for e in editors
            )
            parts.append(f"edited by {ed_names},")
        if publisher:
            parts.append(f"{publisher},")
        if year:
            parts.append(year + ",")
        if pages:
            parts.append(f"pp. {pages}.")

    elif item_type in ("book", "thesis", "report"):
        editors = [c for c in creators if c.get("creatorType") == "editor"]
        authors = [c for c in creators if c.get("creatorType") == "author"]
        if editors and authors:
            ed_names = ", ".join(
                f"{e.get('firstName','')} {e.get('lastName','')}".strip()
                for e in editors
            )
            parts.append(f"Edited by {ed_names},")
        if publisher:
            parts.append(f"{publisher},")
        if year:
            parts.append(year + ".")

    elif item_type in ("webpage", "blogPost"):
        if website:
            parts.append(f"*{website}*,")
        if year:
            parts.append(year + ".")
        if url:
            parts.append(url + ".")

    else:
        if publisher:
            parts.append(f"{publisher},")
        if year:
            parts.append(year + ".")

    # DOI / URL — append for any item type that has one,
    # but skip webpage/blogPost (URL already emitted above)
    if item_type not in ("webpage", "blogPost") and (doi or url):
        loc = f"https://doi.org/{doi}" if doi else url
        parts.append(loc + ".")

    return " ".join(parts)

# ── HTML generation ───────────────────────────────────────────────────────────

HTML_TEMPLATE = string.Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title_tag}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Gudea:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    $h1
    <p class="meta">
      $count item$plural &middot; last synced $timestamp
    </p>
  </header>

  <main>
    <div class="controls">
      <input type="search" id="search" placeholder="Search bibliography&hellip;" aria-label="Search bibliography">
    </div>

    <ol class="bibliography" id="bibliography">
$items
    </ol>

    <p class="empty-msg" id="empty-msg" hidden>No items match your search.</p>
  </main>

  <script>
    const search = document.getElementById('search');
    const bibliography = document.getElementById('bibliography');
    const emptyMsg = document.getElementById('empty-msg');
    const items = Array.from(bibliography.querySelectorAll('li'));

    function applyFilters() {
      const q = search.value.toLowerCase();
      let visible = 0;
      items.forEach(li => {
        const text = li.dataset.search || '';
        const show = !q || text.includes(q);
        li.hidden = !show;
        if (show) visible++;
      });
      emptyMsg.hidden = visible > 0;
    }

    search.addEventListener('input', applyFilters);
  </script>
</body>
</html>
""")

ITEM_TEMPLATE = """\
      <li data-search="{search}">
        <p class="citation">{citation}</p>
      </li>"""

def linkify(text):
    """Wrap bare http/https URLs in <a> tags. Trailing punctuation excluded from href."""
    return re.sub(
        r'(?<!["\'])(https?://[^\s<>"]+?)([.,;:!?)]*(?=\s|$))',
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>\2',
        text
    )

def italicize(citation_text):
    """Convert *text* → <em>text</em>, escape HTML, then linkify URLs."""
    parts = re.split(r'\*([^*]+)\*', citation_text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(f"<em>{escape(part)}</em>")
        else:
            result.append(linkify(escape(part)))
    return "".join(result)

def render_items(items):
    rendered = []
    for item in items:
        data = item.get("data", {})
        citation = format_mla(data)

        search_text = (
            data.get("title", "") + " " +
            data.get("websiteTitle", "") + " " +
            data.get("blogTitle", "") + " " +
            " ".join(
                f"{c.get('lastName','')} {c.get('firstName','')}"
                for c in data.get("creators", [])
            )
        ).lower()

        rendered.append(ITEM_TEMPLATE.format(
            search=escape(search_text),
            citation=italicize(citation),
        ))
    return "\n".join(rendered)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    errors = []
    if not API_KEY:    errors.append("ZOTERO_API_KEY")
    if not USER_ID:    errors.append("ZOTERO_USER_ID")
    if not COLLECTION: errors.append("ZOTERO_COLLECTION")
    if errors:
        print(f"Error: missing environment variable(s): {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching collection {COLLECTION} …")
    items = fetch_all_items(COLLECTION)
    print(f"  {len(items)} item(s) retrieved.")

    def sort_key(item):
        d = item.get("data", {})
        item_type = d.get("itemType", "")
        creators = d.get("creators", [])
        authors = [c for c in creators if c.get("creatorType") == "author"]

        # Webpages: alphabetize by website title, not author
        if item_type in ("webpage", "blogPost"):
            primary = d.get("websiteTitle", "") or d.get("blogTitle", "") or d.get("title", "")
            last = primary.lower().strip()
            for article in ("the ", "a ", "an "):
                if last.startswith(article):
                    last = last[len(article):]
                    break
            return (last or "zzzz", "")

        primary = (authors or creators or [{}])[0]
        last = (primary.get("lastName") or primary.get("name") or "").lower().strip()
        title = d.get("title", "").lower().strip()
        for article in ("the ", "a ", "an "):
            if title.startswith(article):
                title = title[len(article):]
                break
        return (last or "zzzz", title)

    items.sort(key=sort_key)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = len(items)
    plural = "" if count == 1 else "s"

    title_tag = escape(PAGE_TITLE) if PAGE_TITLE else "Bibliography"
    h1 = f"<h1>{escape(PAGE_TITLE)}</h1>" if PAGE_TITLE else ""

    html = HTML_TEMPLATE.substitute(
        title_tag=title_tag,
        h1=h1,
        count=count,
        plural=plural,
        timestamp=timestamp,
        items=render_items(items),
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
