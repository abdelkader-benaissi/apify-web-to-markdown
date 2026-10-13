# Web to Markdown

Turn any web page into clean, LLM-ready **Markdown** over plain HTTP — no headless browser, no waiting. Built for **AI agents** and **RAG pipelines** that need page content as compact, structured text instead of raw HTML.

Feed it one or more URLs and get back one dataset row per page: the converted Markdown plus title, meta description, author, publish date, final URL (after redirects), HTTP status and character count.

## Why agents need this

Raw HTML is 5–10× larger than the text an LLM actually needs, and full of nav bars, cookie banners, scripts and ads. This actor extracts the **main article content** (readability, with `<article>`/`<main>` fallbacks), strips the noise, absolutizes links, and returns tight Markdown — ready to drop into a prompt, a vector store, or a dataset.

And because it's pure HTTP, a page converts in about a second — fast enough to call mid-reasoning-loop, unlike browser-based scrapers that need a container and a browser to boot.

## What it does

- **HTTP-only fetching** — 30s timeout, browser-like User-Agent, follows redirects. No browser overhead.
- **Smart content extraction** — readability first, then `<article>`/`<main>`, then `<body>`; scripts, styles, nav, footers, asides and forms are stripped.
- **Metadata** — page title, meta/OG description, author, `article:published_time` when present.
- **Per-page truncation** — Markdown capped at `maxChars` (default 20,000) so agent context stays bounded.
- **Batch** — one URL per line; one bad URL never kills the batch, failures are reported per row.
- **Safe by default** — only public `http(s)` URLs are fetched; hosts resolving to private, loopback or link-local IPs are refused (SSRF guard).

## Input

| Field | Description |
|---|---|
| `urls` | URLs to convert, one per line (required) |
| `maxChars` | Max Markdown characters per page (default 20,000) |
| `includeImages` | Keep `![alt](url)` image references (default on) |

Example input:

```json
{
  "urls": "https://example.com\nhttps://en.wikipedia.org/wiki/Web_scraping",
  "maxChars": 20000,
  "includeImages": true
}
```

## Output

One dataset row per URL:

| Field | Description |
|---|---|
| `url` / `finalUrl` | Requested URL / URL after redirects |
| `statusCode` | HTTP status of the fetch |
| `title`, `description`, `author`, `publishedAt` | Page metadata |
| `markdown` | Clean Markdown of the main content |
| `charCount` | Length of the Markdown in characters |
| `ok` / `reason` | Success flag; failure reason when `ok` is false |

## Pricing

| Event | Price |
|---|---|
| Page converted | **$0.003** per page successfully converted to Markdown |

You are only charged for pages that convert successfully — failed fetches cost nothing. (Apify platform usage costs are paid by you as usual.)
