"""Lightweight sitemap.xml discovery. Best-effort: if missing or malformed, return empty."""

import logging
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from llms_txt_worker.crawler.fetcher import SSRFError, resolve_and_validate, validate_url

logger = logging.getLogger(__name__)

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

MAX_SITEMAP_SIZE = 1024 * 1024  # 1 MB


async def discover_sitemap_urls(base_url: str, client: httpx.AsyncClient) -> list[str]:
    """Fetch sitemap.xml and extract URLs. Returns empty list on any failure."""
    parsed = urlparse(base_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"

    try:
        validate_url(sitemap_url)
        if parsed.hostname:
            await resolve_and_validate(parsed.hostname)

        response = await client.get(sitemap_url, follow_redirects=False, timeout=10)
        if response.status_code != 200:
            return []

        content_length = response.headers.get("content-length", "")
        if content_length.isdigit() and int(content_length) > MAX_SITEMAP_SIZE:
            logger.debug("Sitemap too large (%s bytes), skipping", content_length)
            return []

        body = response.text
        if len(body) > MAX_SITEMAP_SIZE:
            logger.debug("Sitemap body too large (%d bytes), skipping", len(body))
            return []

        root = ElementTree.fromstring(body)
    except SSRFError:
        return []
    except Exception:
        logger.debug("Failed to fetch/parse sitemap.xml from %s", sitemap_url)
        return []

    urls: list[str] = []

    for url_elem in root.findall("sm:url", SITEMAP_NS):
        loc = url_elem.find("sm:loc", SITEMAP_NS)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    logger.info("Discovered %d URLs from sitemap.xml", len(urls))
    return urls
