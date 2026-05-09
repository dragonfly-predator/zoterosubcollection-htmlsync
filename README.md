# zoterosubcollection-htmlsync

# Zotero → GitHub Pages Sync

Automatically publishes a formatted MLA 9th-edition bibliography from a Zotero subcollection to a GitHub Pages site. The page includes full-text search.

## Files

| File | Purpose |
|---|---|
| `generate.py` | Fetches Zotero API, writes `index.html` |
| `style.css` | Page styles |
| `.github/workflows/sync.yml` | Runs the script daily and commits the result |

---

## Setup

### 1. Create the repository

Create a new GitHub repository (public or private). Push these files to the `main` branch.

### 2. Enable GitHub Pages

In your repo: **Settings → Pages → Source → Deploy from a branch → `main` / `(root)`**.

### 3. Get your Zotero credentials

| Value | Where to find it |
|---|---|
| **API key** | [zotero.org/settings/keys](https://www.zotero.org/settings/keys) → *Create new private key* (needs read-only library access) |
| **User ID** | Same page — shown above the key list |
| **Collection key** | Open your Zotero collection in the web library. The URL looks like `zotero.org/users/USERID/collections/XXXXXXXX` — the 8-character part at the end is the collection key |

### 4. Add GitHub Secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**.

Add these three secrets:

- `ZOTERO_API_KEY`
- `ZOTERO_USER_ID`
- `ZOTERO_COLLECTION`

### 5. Optional configuration

You can set these as environment variables in the workflow file (`sync.yml`) if you want to override defaults:

| Variable | Default | Description |
|---|---|---|
| `ZOTERO_LIBRARY_TYPE` | `user` | Use `group` for group libraries |
| `PAGE_TITLE` | *(none)* | Heading shown on the page |
| `OUTPUT_FILE` | `index.html` | Output filename |

### 6. Run manually to test

Go to **Actions → Sync Zotero → Run workflow**. If successful, `index.html` will be committed and your Pages site will update within a minute.

---

## Schedule

The workflow runs daily at 04:00 UTC by default. To change the schedule, edit the `cron` line in `.github/workflows/sync.yml`. Use [crontab.guru](https://crontab.guru) to build a cron expression.

---

## Notes

- Only top-level items are fetched; attachments and notes are excluded.
- Items are sorted alphabetically by first author's last name, then title.
- For webpage and blog post items, entries are sorted and displayed by site/blog title rather than individual page title.
- MLA formatting covers journal articles, books, book sections, webpages, blog posts, theses, and reports. Other item types fall back to a generic format.
- Titles are italicized using `<em>` tags; URLs and DOIs are hyperlinked.

