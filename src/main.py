"""Web to Markdown actor: convert web pages to clean, LLM-ready Markdown.

Each public URL is fetched over plain HTTP (no headless browser — speed is the
point), the main article content is extracted with readability (falling back to
<article>/<main>, then <body>), scripts/styles/nav/footer are stripped, and the
result is converted to Markdown.

Pay-per-event charges ("page-converted") are emitted only for successful
conversions, never for failures.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from apify import Actor
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readability import Document

EVENT_PAGE = 'page-converted'

REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

NOISE_TAGS = ('script', 'style', 'nav', 'footer', 'aside', 'noscript',
              'form', 'iframe', 'svg', 'canvas', 'button')


async def check_public_url(url: str) -> tuple[bool, str]:
    """SSRF guard: only allow http(s) URLs that resolve to public IPs."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, 'malformed URL'
    if parsed.scheme not in ('http', 'https'):
        return False, f"unsupported scheme '{parsed.scheme}' (only http/https allowed)"
    host = parsed.hostname
    if not host:
        return False, 'missing hostname'
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return False, 'DNS resolution failed'
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False, f'resolves to non-public IP {ip}'
    return True, ''


def extract_metadata(soup: BeautifulSoup) -> dict:
    """Pull title/description/author/publishedAt from <title> and meta tags."""
    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    description = ''
    author = ''
    published_at = ''
    for meta in soup.find_all('meta'):
        name = (meta.get('name') or meta.get('property') or '').lower()
        content = (meta.get('content') or '').strip()
        if not content:
            continue
        if name in ('description', 'og:description', 'twitter:description') and not description:
            description = content
        elif name in ('author', 'article:author', 'twitter:creator') and not author:
            author = content
        elif name in ('article:published_time', 'article:modified_time', 'date',
                      'publish_date', 'publishdate') and not published_at:
            published_at = content
        elif name == 'og:title' and not title:
            title = content
    return {'title': title, 'description': description,
            'author': author, 'publishedAt': published_at}


def absolutize_links(node: BeautifulSoup, base_url: str) -> None:
    """Rewrite relative href/src to absolute URLs so Markdown links survive."""
    for tag in node.find_all('a', href=True):
        tag['href'] = urljoin(base_url, tag['href'])
    for tag in node.find_all('img', src=True):
        tag['src'] = urljoin(base_url, tag['src'])


def extract_markdown(html: str, base_url: str, include_images: bool) -> tuple[str, dict]:
    """Extract main content and convert to Markdown. Returns (markdown, meta)."""
    soup = BeautifulSoup(html, 'lxml')
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    meta = extract_metadata(soup)

    # 1) readability, 2) <article>/<main>, 3) body
    content = None
    try:
        doc = Document(str(soup))
        frag = BeautifulSoup(doc.summary(html_partial=True), 'lxml')
        if len(frag.get_text(strip=True)) >= 200:
            content = frag
    except Exception:
        content = None
    if content is None:
        for selector in ('article', 'main', '[role="main"]'):
            node = soup.select_one(selector)
            if node is not None and len(node.get_text(strip=True)) >= 200:
                content = node
                break
    if content is None:
        content = soup.body or soup

    if not include_images:
        for img in content.find_all('img'):
            img.decompose()
    else:
        absolutize_links(content, base_url)
    # Always absolutize links; images handled above.
    for tag in content.find_all('a', href=True):
        tag['href'] = urljoin(base_url, tag['href'])

    markdown = md(str(content), heading_style='ATX', bullets='-').strip()
    # Collapse 3+ blank lines into two.
    lines = markdown.splitlines()
    cleaned: list[str] = []
    blanks = 0
    for line in lines:
        if line.strip():
            blanks = 0
            cleaned.append(line.rstrip())
        else:
            blanks += 1
            if blanks <= 1:
                cleaned.append('')
    return '\n'.join(cleaned).strip(), meta


def fail_item(url: str, reason: str, status: int | None = None) -> dict:
    item = {'url': url, 'finalUrl': '', 'statusCode': status,
            'title': '', 'description': '', 'author': '', 'publishedAt': '',
            'markdown': '', 'charCount': 0, 'ok': False, 'reason': reason}
    return item


async def convert_one(client: httpx.AsyncClient, url: str,
                      max_chars: int, include_images: bool) -> dict:
    """Fetch one URL and convert it. Never raises; failures become items."""
    ok, reason = await check_public_url(url)
    if not ok:
        return fail_item(url, f'blocked: {reason}')
    try:
        resp = await client.get(url, timeout=30.0, follow_redirects=True)
    except httpx.TimeoutException:
        return fail_item(url, 'fetch timed out after 30s')
    except httpx.HTTPError as exc:
        return fail_item(url, f'fetch failed: {type(exc).__name__}')
    except Exception as exc:  # defensive: never kill the batch
        return fail_item(url, f'fetch failed: {type(exc).__name__}')

    status = resp.status_code
    if status >= 400:
        return fail_item(url, f'HTTP {status}', status)
    content_type = resp.headers.get('content-type', '').lower()
    if not any(t in content_type for t in ('html', 'text', 'xml')):
        return fail_item(url, f'unsupported content type: {content_type}', status)

    final_url = str(resp.url)
    try:
        markdown, meta = extract_markdown(resp.text, final_url, include_images)
    except Exception as exc:
        return fail_item(url, f'extraction failed: {type(exc).__name__}', status)
    if len(markdown) < 50:
        return fail_item(url, 'no readable content found', status)
    if len(markdown) > max_chars:
        markdown = markdown[:max_chars].rstrip() + '\n\n…[truncated]'

    return {
        'url': url,
        'finalUrl': final_url,
        'statusCode': status,
        'title': meta['title'],
        'description': meta['description'],
        'author': meta['author'],
        'publishedAt': meta['publishedAt'],
        'markdown': markdown,
        'charCount': len(markdown),
        'ok': True,
        'reason': '',
    }


async def charge_event(event_name: str) -> None:
    """Bill one pay-per-event charge. Never let billing break the run."""
    try:
        await Actor.charge(event_name=event_name)
    except Exception as exc:
        Actor.log.warning(f'Pay-per-event charge {event_name!r} failed: {exc}')


def parse_urls(raw) -> list[str]:
    if isinstance(raw, str):
        return [u.strip() for u in raw.splitlines() if u.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(u).strip() for u in raw if str(u).strip()]
    return []


def build_client() -> httpx.AsyncClient:
    """Build the HTTP client.

    Falls back to ignoring environment proxies if the environment's proxy
    config is malformed (e.g. bare IPv6 literals in no_proxy, which some
    httpx versions cannot parse) — a broken proxy config must not kill runs.
    """
    try:
        return httpx.AsyncClient(headers=REQUEST_HEADERS,
                                 follow_redirects=True, timeout=30.0)
    except Exception as exc:
        Actor.log.warning(f'Unusable proxy environment ({exc}); '
                          'continuing without env proxies.')
        return httpx.AsyncClient(headers=REQUEST_HEADERS,
                                 follow_redirects=True, timeout=30.0,
                                 trust_env=False)


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        urls = parse_urls(inp.get('urls'))
        try:
            max_chars = int(inp.get('maxChars') or 20000)
        except (TypeError, ValueError):
            max_chars = 20000
        max_chars = max(100, min(max_chars, 200000))
        include_images = bool(inp.get('includeImages', True))

        if not urls:
            await Actor.set_value('OUTPUT', {
                'total': 0, 'succeeded': 0, 'failed': 0,
                'error': 'no URLs provided',
            })
            return

        succeeded = 0
        failed = 0
        async with build_client() as client:
            for url in urls:
                item = await convert_one(client, url, max_chars, include_images)
                if item['ok']:
                    succeeded += 1
                    # Charge only after a successful conversion.
                    await charge_event(EVENT_PAGE)
                else:
                    failed += 1
                await Actor.push_data(item)

        await Actor.set_value('OUTPUT', {
            'total': len(urls),
            'succeeded': succeeded,
            'failed': failed,
        })
