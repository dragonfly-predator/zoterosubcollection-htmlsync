#!/usr/bin/env python3
"""
Fetches a Zotero subcollection via the Web API and generates index.html with MLA citations and tags.

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
import sys
import json
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
PAGE_TITLE    = os.environ.get("PAGE_TITLE", "Zotero Library")

BASE_URL = f"https://api.zotero.org/{LIBRARY_TYPE}s/{USER_ID}"

# ── Zotero API helpers ────────────────────────────────────────────────────────

def zotero_get(path, params=None):
    """GET from the Zotero API, returns parsed JSON."""
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Zotero-API-Key": API_KEY,
        "Zotero-API-Version": "3",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def fetch_all_items(collection_key):
    """Fetch all items in a collection, handling pagination."""
    items = []
    start = 0
    limit = 100
    while True:
        batch = zotero_get(f"/collections/{collection_key}/items/top", {
            "limit": limit,
            "start": start,
            "itemType": "-attachment || -note",
        })
        if not batch:
            break
        items.extend(batch)
        if len(batch) < limit:
            break
        start += limit
    return items

# ── MLA formatting ────────────────────────────────────────────────────────────

def format_author_mla(creator):
    """Format a single creator for MLA."""
    if "lastName" in creator and "firstName" in creator:
        return f"{creator['lastName']}, {creator['firstName']}"
    return creator.get("name", "")

def format_author_normal(creator):
    """Format a creator in normal (non-inverted) order: First Last."""
    if "firstName" in creator and "lastName" in creator:
        return f"{creator['firstName']} {creator['lastName']}".strip()
    return creator.get("name", "")

def format_authors_mla(creators):
    """Format a list of creators in MLA 9th-edition style.

    - 1 author:  Last, First.
    - 2–3 authors: Last, First, First Last, and First Last.
    - 4+ authors: Last, First, et al.
    """
    authors = [c for c in creators if c.get("creatorType") == "author"]
    if not authors:
        authors = creators  # fallback
    if not authors:
        return ""
    if len(authors) == 1:
        return format_author_mla(authors[0])
    if len(authors) <= 3:
        # First author inverted; remaining in normal order
        parts = [format_author_mla(authors[0])]
        for a in authors[1:-1]:
            parts.append(format_author_normal(a))
        parts_str = ", ".join(parts)
        return f"{parts_str}, and {format_author_normal(authors[-1])}"
    # 4+ authors: et al.
    return f"{format_author_mla(authors[0])}, et al."

def format_mla(data):
    """
    Build an MLA 9th-edition citation string for common item types.
    Returns a plain-text string (HTML escaping happens later).
    """
    item_type  = data.get("itemType", "")
    title      = data.get("title", "Untitled")
    creators   = data.get("creators", [])
    year       = (data.get("date") or "")[:4]
    url        = data.get("url", "")
    doi        = data.get("DOI", "")
    publisher  = data.get("publisher", "") or data.get("institution", "")
    pub_place  = data.get("place", "")
    journal    = data.get("publicationTitle", "") or data.get("journalAbbreviation", "")
    volume     = data.get("volume", "")
    issue      = data.get("issue", "")
    pages      = data.get("pages", "")
    website    = data.get("websiteTitle", "") or data.get("blogTitle", "")
    accessed   = data.get("accessDate", "")

    authors_str = format_authors_mla(creators)

    parts = []

    # Authors
    if authors_str:
        parts.append(authors_str + ".")

    # Title
    if item_type in ("journalArticle", "magazineArticle", "newspaperArticle",
                     "bookSection", "conferencePaper", "blogPost", "webpage"):
        # Period goes inside quotes unless title already ends in punctuation
        end = "" if title.rstrip() and title.rstrip()[-1] in ".?!" else "."
        parts.append(f'"{title}{end}"')
    else:
        parts.append(f"*{title}*.")

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
                # Close the entry with a period if there are no pages
                if parts and parts[-1].endswith(","):
                    parts[-1] = parts[-1][:-1] + "."
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
            pub = f"{pub_place + ': ' if pub_place else ''}{publisher},"
            parts.append(pub)
        if year:
            parts.append(year + ",")
        if pages:
            parts.append(f"pp. {pages}.")
    elif item_type in ("book", "thesis", "report"):
        # If the book has an author AND an editor, place editor after title
        editors = [c for c in creators if c.get("creatorType") == "editor"]
        authors = [c for c in creators if c.get("creatorType") == "author"]
        if editors and authors:
            ed_names = ", ".join(
                f"{e.get('firstName','')} {e.get('lastName','')}".strip()
                for e in editors
            )
            parts.append(f"Edited by {ed_names},")
        if pub_place and publisher:
            parts.append(f"{pub_place}: {publisher},")
        elif publisher:
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
        # Generic fallback
        if publisher:
            parts.append(f"{publisher},")
        if year:
            parts.append(year + ".")

    # DOI / URL fallback for academic items
    if item_type in ("journalArticle", "conferencePaper") and (doi or url):
        loc = f"https://doi.org/{doi}" if doi else url
        parts.append(loc + ".")

    return " ".join(parts)

# ── HTML generation ───────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p class="meta">
      {count} item{plural} &middot; last synced {timestamp}
    </p>
  </header>

  <main>
    <div class="controls">
      <input type="search" id="search" placeholder="Filter by title, author, or tag&hellip;" aria-label="Search">
      <div class="tag-filters" id="tag-filters"></div>
    </div>

    <ol class="bibliography" id="bibliography">
{items}
    </ol>

    <p class="empty-msg" id="empty-msg" hidden>No items match your filter.</p>
  </main>

  <script>
    const search = document.getElementById('search');
    const tagFilters = document.getElementById('tag-filters');
    const bibliography = document.getElementById('bibliography');
    const emptyMsg = document.getElementById('empty-msg');
    const items = Array.from(bibliography.querySelectorAll('li'));

    // Build tag buttons from unique tags across all items
    const allTags = new Set();
    items.forEach(li => {
      (li.dataset.tags || '').split('|').filter(Boolean).forEach(t => allTags.add(t));
    });

    let activeTag = null;

    [...allTags].sort().forEach(tag => {
      const btn = document.createElement('button');
      btn.className = 'tag-btn';
      btn.textContent = tag;
      btn.addEventListener('click', () => {
        if (activeTag === tag) {
          activeTag = null;
          btn.classList.remove('active');
        } else {
          activeTag = tag;
          document.querySelectorAll('.tag-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
        }
        applyFilters();
      });
      tagFilters.appendChild(btn);
    });

    function applyFilters() {
      const q = search.value.toLowerCase();
      let visible = 0;
      items.forEach(li => {
        const text = li.dataset.search || '';
        const tags = (li.dataset.tags || '').split('|');
        const matchesSearch = !q || text.includes(q);
        const matchesTag = !activeTag || tags.includes(activeTag);
        const show = matchesSearch && matchesTag;
        li.hidden = !show;
        if (show) visible++;
      });
      emptyMsg.hidden = visible > 0;
    }

    search.addEventListener('input', applyFilters);
  </script>
</body>
</html>
"""

ITEM_TEMPLATE = """\
      <li data-search="{search}" data-tags="{tags}">
        <p class="citation">{citation}</p>
        {tag_html}
      </li>"""

def italicize(citation_text):
    """Convert *text* markers to <em>text</em>, then escape remaining HTML."""
    import re
    # Split on *...* markers, alternating plain / italic segments
    parts = re.split(r'\*([^*]+)\*', citation_text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # inside *...*
            result.append(f"<em>{escape(part)}</em>")
        else:
            result.append(escape(part))
    return "".join(result)

def build_tag_html(tags):
    if not tags:
        return ""
    spans = "".join(f'<span class="tag">{escape(t)}</span>' for t in tags)
    return f'<div class="tags">{spans}</div>'

def render_items(items):
    rendered = []
    for item in items:
        data = item.get("data", {})
        citation = format_mla(data)
        raw_tags = [t["tag"] for t in data.get("tags", [])]
        tag_html = build_tag_html(raw_tags)
        tags_attr = "|".join(raw_tags)

        # Search index: title + authors (lowercased)
        search_text = (
            data.get("title", "") + " " +
            " ".join(
                f"{c.get('lastName','')} {c.get('firstName','')}"
                for c in data.get("creators", [])
            ) + " " +
            " ".join(raw_tags)
        ).lower()

        rendered.append(ITEM_TEMPLATE.format(
            search=escape(search_text),
            tags=escape(tags_attr),
            citation=italicize(citation),  # handles *italics* → <em>
            tag_html=tag_html,
        ))
    return "\n".join(rendered)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    errors = []
    if not API_KEY:   errors.append("ZOTERO_API_KEY")
    if not USER_ID:   errors.append("ZOTERO_USER_ID")
    if not COLLECTION: errors.append("ZOTERO_COLLECTION")
    if errors:
        print(f"Error: missing environment variable(s): {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching collection {COLLECTION} …")
    items = fetch_all_items(COLLECTION)
    print(f"  {len(items)} item(s) retrieved.")

    # Sort by first author last name, then title
    def sort_key(item):
        d = item.get("data", {})
        authors = [c for c in d.get("creators", []) if c.get("creatorType") == "author"]
        last = authors[0].get("lastName", "zzzz").lower() if authors else "zzzz"
        return (last, d.get("title", "").lower())

    items.sort(key=sort_key)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    count = len(items)
    plural = "" if count == 1 else "s"

    html = HTML_TEMPLATE.format(
        title=escape(PAGE_TITLE),
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
