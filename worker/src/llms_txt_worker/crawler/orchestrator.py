"""Priority-based crawl orchestrator with bounded depth, page count, and concurrency.

Uses a scored frontier (heapq) instead of plain BFS so high-value hub pages
are fetched before deep inventory/marketplace/article pages. A per-prefix
quota prevents any single top-level path from monopolizing the crawl budget.
"""

import asyncio
import heapq
import logging
import re
import time
from collections import Counter
from urllib.parse import urlparse

import httpx

from llms_txt_worker.config import settings
from llms_txt_worker.crawler.fetcher import SSRFError, safe_fetch
from llms_txt_worker.crawler.robots import USER_AGENT, fetch_robots, is_allowed
from llms_txt_worker.crawler.sitemap import discover_sitemap_urls
from llms_txt_worker.extraction.parser import (
    extract_internal_links,
    extract_metadata,
    extract_site_info,
)
from llms_txt_worker.persistence.models import PageMetadata

logger = logging.getLogger(__name__)

_SKIP_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3",
    ".zip", ".tar", ".gz", ".exe", ".dmg", ".xml", ".json", ".rss",
})

_SKIP_PATH_PATTERNS = frozenset({
    "/login", "/signin", "/signup", "/register", "/logout",
    "/auth", "/oauth", "/admin", "/wp-admin", "/cart", "/checkout",
    "/search", "/404", "/500", "/live-news",
})

_DATED_ARTICLE_RE = re.compile(r"/20\d{2}/\d{2}/\d{2}/")
_GENERIC_VIDEO_RE = re.compile(r"/videos/title-\d+")
_SITEMAP_INDEX_RE = re.compile(r"/sitemap[_-]?\d{4}\.html$", re.IGNORECASE)
_PREFERRED_PATH_PREFIXES = (
    "/docs",
    "/documentation",
    "/help",
    "/guide",
    "/guides",
    "/tutorial",
    "/tutorials",
    "/api",
    "/reference",
    "/cli",
    "/support",
    "/faq",
    "/about",
    "/account",
    "/enterprise",
    "/changelog",
)
_DEPRIORITIZED_PATH_PREFIXES = (
    "/marketplace",
    "/product",
    "/pricing",
    "/careers",
    "/download",
    "/blog",
)
_LOW_VALUE_MARKERS = (
    "access to this page has been denied",
    "px-captcha",
)

MAX_PAGES_PER_PREFIX = 15


def _has_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def _should_skip_url(url: str) -> bool:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    if any(path_lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return True

    if any(pattern in path_lower for pattern in _SKIP_PATH_PATTERNS):
        return True

    if _DATED_ARTICLE_RE.search(path_lower):
        return True

    if _GENERIC_VIDEO_RE.search(path_lower):
        return True

    if _SITEMAP_INDEX_RE.search(path_lower):
        return True

    if parsed.query and parsed.query.count("=") > 2:
        return True

    return False


def _url_priority(url: str) -> tuple[int, int, str]:
    """Score a URL for the priority frontier. Lower = fetched sooner."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower().rstrip("/")
    depth = len([segment for segment in path_lower.split("/") if segment])

    if path_lower in ("", "/"):
        rank = 0
    elif _has_prefix(path_lower, _PREFERRED_PATH_PREFIXES):
        rank = 0
    elif _has_prefix(path_lower, _DEPRIORITIZED_PATH_PREFIXES):
        rank = 2
    else:
        rank = 1

    return (rank, depth, path_lower)


def _top_level_prefix(url: str) -> str:
    """Extract the first path segment as a section key for quota tracking."""
    segments = [s for s in urlparse(url).path.lower().split("/") if s]
    return segments[0] if segments else ""


def _should_skip_page(page: PageMetadata) -> bool:
    if page.status_code >= 400:
        return True

    haystack = f"{page.title}\n{page.description}".lower()
    return any(marker in haystack for marker in _LOW_VALUE_MARKERS)


async def crawl(url: str) -> tuple[list[PageMetadata], str, str]:
    """Crawl a website starting from `url`. Returns (pages, site_title, site_summary)."""
    parsed_base = urlparse(url)
    base_host = parsed_base.hostname
    if not base_host:
        raise ValueError(f"Cannot determine host from URL: {url}")
    base_host = base_host.lower()

    pages: list[PageMetadata] = []
    visited: set[str] = set()
    prefix_counts: Counter[str] = Counter()
    site_title = ""
    site_summary = ""

    # priority frontier: each entry is (priority_tuple, tie_breaker, url, depth)
    frontier: list[tuple[tuple[int, int, str], int, str, int]] = []
    seq = 0

    def push(frontier_url: str, depth: int) -> None:
        nonlocal seq
        priority = _url_priority(frontier_url)
        heapq.heappush(frontier, (priority, seq, frontier_url, depth))
        seq += 1

    def pop() -> tuple[str, int]:
        _, _, frontier_url, depth = heapq.heappop(frontier)
        return frontier_url, depth

    start_time = time.monotonic()
    semaphore = asyncio.Semaphore(settings.max_concurrency)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        timeout=settings.per_request_timeout,
    ) as client:
        robots = await fetch_robots(url, client)

        visited.add(url)

        sitemap_urls = await discover_sitemap_urls(url, client)
        for sm_url in sitemap_urls:
            sm_parsed = urlparse(sm_url)
            if sm_parsed.hostname and sm_parsed.hostname.lower() == base_host:
                if sm_url not in visited and not _should_skip_url(sm_url):
                    push(sm_url, 1)
                    visited.add(sm_url)

        push(url, 0)

        while frontier and len(pages) < settings.max_pages:
            elapsed = time.monotonic() - start_time
            if elapsed > settings.total_crawl_timeout:
                logger.warning("Total crawl timeout reached after %.1fs", elapsed)
                break

            batch_size = min(
                settings.max_concurrency,
                settings.max_pages - len(pages),
                len(frontier),
            )

            batch: list[tuple[str, int]] = []
            while frontier and len(batch) < batch_size:
                candidate_url, depth = pop()
                prefix = _top_level_prefix(candidate_url)
                if prefix and prefix_counts[prefix] >= MAX_PAGES_PER_PREFIX:
                    continue
                batch.append((candidate_url, depth))

            if not batch:
                break

            async def fetch_one(fetch_url: str, depth: int) -> PageMetadata | None:
                nonlocal site_title, site_summary, base_host

                async with semaphore:
                    if not is_allowed(robots, fetch_url):
                        logger.debug("Blocked by robots.txt: %s", fetch_url)
                        return None
                    try:
                        result = await safe_fetch(fetch_url, client)
                    except SSRFError as exc:
                        logger.debug("SSRF blocked: %s - %s", fetch_url, exc)
                        return None
                    except httpx.HTTPError as exc:
                        logger.debug("HTTP error fetching %s: %s", fetch_url, exc)
                        return None

                    if depth == 0:
                        site_title, site_summary = extract_site_info(result.body)
                        resolved_host = urlparse(result.url).hostname
                        if resolved_host and resolved_host.lower() != base_host:
                            logger.info(
                                "Host changed after redirect: %s -> %s",
                                base_host, resolved_host.lower(),
                            )
                            base_host = resolved_host.lower()
                    else:
                        resolved_host = urlparse(result.url).hostname
                        if resolved_host and resolved_host.lower() != base_host:
                            logger.debug(
                                "Skipping page redirected off-site: %s -> %s",
                                fetch_url,
                                result.url,
                            )
                            return None

                    page = extract_metadata(
                        result.url, result.body, depth, result.status_code
                    )
                    if _should_skip_page(page):
                        return None

                    if depth < settings.max_depth:
                        new_links = extract_internal_links(
                            result.body, result.url, base_host
                        )
                        for link in new_links:
                            if link not in visited and not _should_skip_url(link):
                                visited.add(link)
                                push(link, depth + 1)

                    return page

            tasks = [fetch_one(u, d) for u, d in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, PageMetadata):
                    prefix = _top_level_prefix(result.url)
                    prefix_counts[prefix] += 1
                    pages.append(result)
                elif isinstance(result, Exception):
                    logger.debug("Crawl task exception: %s", result)

    logger.info(
        "Crawl complete: %d pages in %.1fs",
        len(pages),
        time.monotonic() - start_time,
    )
    return pages, site_title, site_summary
