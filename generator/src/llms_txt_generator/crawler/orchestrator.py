"""Priority-BFS crawl orchestrator.

The homepage is fetched first and its links are seeded into the BFS
frontier.  This ensures structurally important pages — those the site
itself links from its homepage — are crawled first, and sub-pages are
discovered naturally through link-following.

Safety bounds: concurrency, per-prefix quota, page limit, timeout,
robots.txt enforcement, and SSRF protection.
"""

import asyncio
import dataclasses
import heapq
import logging
import re
import time
from collections import Counter
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from llms_txt_generator.config import settings
from llms_txt_generator.crawler.fetcher import SSRFError, safe_fetch
from llms_txt_generator.crawler.robots import USER_AGENT, fetch_robots, is_allowed
from llms_txt_generator.extraction.parser import (
    extract_internal_links,
    extract_metadata,
    extract_site_info,
)
from llms_txt_generator.persistence.models import PageMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL filtering & priority
# ---------------------------------------------------------------------------

_SKIP_EXTENSIONS = frozenset({
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".bmp", ".tif", ".tiff", ".avif",
    # audio / video
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".ogg", ".wav", ".m4a", ".m4v",
    # fonts
    ".woff", ".woff2", ".ttf", ".eot",
    # documents / archives
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2",
    # scripts / executables / data
    ".css", ".js", ".wasm",
    ".exe", ".dmg", ".msi", ".apk",
    ".xml", ".json", ".rss", ".csv",
})

_SKIP_PATH_PATTERNS = frozenset({
    "/login", "/signin", "/signup", "/register", "/logout",
    "/auth", "/oauth", "/admin", "/wp-admin",
    "/cart", "/checkout",
    "/search", "/404", "/500", "/blocked",
})

_DATED_ARTICLE_RE = re.compile(r"/\d{4}/\d{2}/\d{2}/")
_SITEMAP_INDEX_RE = re.compile(r"/sitemap[_-]?\d{4}\.html$", re.IGNORECASE)
_LOCALE_PREFIX_RE = re.compile(r"^/[a-z]{2}(?:[_-][a-z]{2,3})?(/|$)")
_UUID_SEGMENT_RE = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(/|$)", re.IGNORECASE)
_LOW_VALUE_MARKERS = (
    "access to this page has been denied",
    "px-captcha",
    "robot or human",
    "are you a robot",
    "verify you are human",
    "please verify you are a human",
    "complete the security check",
    "checking your browser",
    "just a moment",
    "there is no page here",
    "page not found",
    "page cannot be found",
    "uh oh",
    "something went wrong",
)
_TEMPLATE_TITLE_RE = re.compile(r"__\w+__")

MAX_PAGES_PER_PREFIX = 10


def _should_skip_url(url: str) -> bool:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    if any(path_lower.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return True
    if any(pattern in path_lower for pattern in _SKIP_PATH_PATTERNS):
        return True
    if _DATED_ARTICLE_RE.search(path_lower):
        return True
    if _SITEMAP_INDEX_RE.search(path_lower):
        return True
    if _LOCALE_PREFIX_RE.match(path_lower):
        return True
    if _UUID_SEGMENT_RE.search(path_lower):
        return True
    if parsed.query and parsed.query.count("=") > 2:
        return True
    return False


def _url_priority(url: str) -> int:
    """Score a URL for the priority frontier. Lower = fetched sooner.

    Uses URL depth (number of path segments) as the sole signal —
    shallower pages are structurally more important.  Ties are broken
    by the heap's sequence counter (FIFO), avoiding alphabetical path
    bias that would starve later-alphabet sections.
    """
    parsed = urlparse(url)
    path_lower = parsed.path.lower().rstrip("/")
    return len([segment for segment in path_lower.split("/") if segment])


def _top_level_prefix(url: str) -> str:
    """Extract the first path segment as a section key for quota tracking."""
    segments = [s for s in urlparse(url).path.lower().split("/") if s]
    return segments[0] if segments else ""


def _should_skip_page(page: PageMetadata) -> bool:
    if page.status_code >= 400:
        return True
    if _TEMPLATE_TITLE_RE.search(page.title):
        return True
    haystack = f"{page.title}\n{page.description}".lower()
    return any(marker in haystack for marker in _LOW_VALUE_MARKERS)


# ---------------------------------------------------------------------------
# Shared crawl statistics
# ---------------------------------------------------------------------------

MAX_TOTAL_FETCHES_MULTIPLIER = 3
BLOCK_DETECTION_MIN_FETCHES = 30
BLOCK_DETECTION_MAX_SUCCESS_RATE = 0.10

@dataclasses.dataclass
class CrawlStats:
    skipped_robots: int = 0
    skipped_errors: int = 0
    skipped_offsite: int = 0
    skipped_quality: int = 0
    total_fetches: int = 0

    @property
    def budget_exhausted(self) -> bool:
        """True when total fetches exceeds a multiple of the page limit."""
        return self.total_fetches >= settings.max_pages * MAX_TOTAL_FETCHES_MULTIPLIER

    def is_aggressively_blocked(self, pages_kept: int) -> bool:
        """True when the site appears to be actively blocking most requests."""
        if self.total_fetches < BLOCK_DETECTION_MIN_FETCHES:
            return False
        success_rate = pages_kept / self.total_fetches
        return success_rate < BLOCK_DETECTION_MAX_SUCCESS_RATE


# ---------------------------------------------------------------------------
# Homepage fetch
# ---------------------------------------------------------------------------

async def _fetch_homepage(
    url: str,
    base_host: str,
    client: httpx.AsyncClient,
    robots: RobotFileParser,
    stats: CrawlStats,
) -> tuple[PageMetadata | None, str, str, str, list[str]]:
    """Fetch the homepage and extract its links.

    Returns (page_or_none, site_title, site_summary, resolved_host, homepage_links).
    Homepage links are the strongest signal for which pages are structurally
    important — they seed the BFS frontier.
    """
    empty: tuple[None, str, str, str, list[str]] = (None, "", "", base_host, [])

    if not is_allowed(robots, url):
        stats.skipped_robots += 1
        logger.info("Blocked by robots.txt: %s", url)
        return empty

    stats.total_fetches += 1
    try:
        result = await safe_fetch(url, client)
    except SSRFError as exc:
        stats.skipped_errors += 1
        logger.warning("SSRF blocked: %s - %s", url, exc)
        return empty
    except httpx.HTTPError as exc:
        stats.skipped_errors += 1
        logger.warning("HTTP error fetching %s: %s", url, exc)
        return empty

    site_title, site_summary = extract_site_info(result.body)
    logger.info(
        "Homepage fetched: status=%d title=%r summary_len=%d",
        result.status_code, site_title[:80], len(site_summary),
    )

    resolved_host = base_host
    rh = urlparse(result.url).hostname
    if rh and rh.lower() != base_host:
        logger.info("Host changed after redirect: %s -> %s", base_host, rh.lower())
        resolved_host = rh.lower()

    homepage_links = extract_internal_links(result.body, result.url, resolved_host)

    page = extract_metadata(result.url, result.body, 0, result.status_code)
    if _should_skip_page(page):
        stats.skipped_quality += 1
        logger.info(
            "Skipped low-quality page: %s (status=%d title=%r)",
            url, page.status_code, page.title[:60] if page.title else "",
        )
        return None, site_title, site_summary, resolved_host, homepage_links

    return page, site_title, site_summary, resolved_host, homepage_links


# ---------------------------------------------------------------------------
# Priority-BFS crawl
# ---------------------------------------------------------------------------

async def _crawl_bfs(
    url: str,
    base_host: str,
    client: httpx.AsyncClient,
    robots: RobotFileParser,
    homepage_links: list[str],
    start_time: float,
    stats: CrawlStats,
) -> list[PageMetadata]:
    """Priority-BFS crawl seeded with homepage links.

    The homepage is already fetched by the caller; its internal links are
    pushed into the frontier at depth 1.  The BFS then follows links
    naturally, discovering sub-pages through the site's own structure.
    """
    pages: list[PageMetadata] = []
    visited: set[str] = set()
    prefix_counts: Counter[str] = Counter()

    frontier: list[tuple[int, int, str, int]] = []
    seq = 0

    def push(frontier_url: str, depth: int) -> None:
        nonlocal seq
        priority = _url_priority(frontier_url)
        heapq.heappush(frontier, (priority, seq, frontier_url, depth))
        seq += 1

    def pop() -> tuple[str, int]:
        _, _, frontier_url, depth = heapq.heappop(frontier)
        return frontier_url, depth

    visited.add(url)

    for link in homepage_links:
        if link not in visited and not _should_skip_url(link):
            push(link, 1)
            visited.add(link)

    semaphore = asyncio.Semaphore(settings.max_concurrency)

    while frontier and len(pages) < settings.max_pages:
        elapsed = time.monotonic() - start_time
        if elapsed > settings.total_crawl_timeout:
            logger.warning("Total crawl timeout reached after %.1fs", elapsed)
            break
        if stats.budget_exhausted:
            logger.warning(
                "Fetch budget exhausted: %d fetches for %d pages (site may be blocking)",
                stats.total_fetches, len(pages),
            )
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
            async with semaphore:
                if not is_allowed(robots, fetch_url):
                    stats.skipped_robots += 1
                    logger.info("Blocked by robots.txt: %s", fetch_url)
                    return None
                stats.total_fetches += 1
                try:
                    result = await safe_fetch(fetch_url, client)
                except SSRFError as exc:
                    stats.skipped_errors += 1
                    logger.warning("SSRF blocked: %s - %s", fetch_url, exc)
                    return None
                except httpx.HTTPError as exc:
                    stats.skipped_errors += 1
                    logger.warning("HTTP error fetching %s: %s", fetch_url, exc)
                    return None

                resolved_host = urlparse(result.url).hostname
                if resolved_host and resolved_host.lower() != base_host:
                    stats.skipped_offsite += 1
                    logger.info(
                        "Skipping page redirected off-site: %s -> %s",
                        fetch_url, result.url,
                    )
                    return None

                if depth < settings.max_depth:
                    new_links = extract_internal_links(
                        result.body, result.url, base_host
                    )
                    for link in new_links:
                        if link not in visited and not _should_skip_url(link):
                            visited.add(link)
                            push(link, depth + 1)

                page = extract_metadata(
                    result.url, result.body, depth, result.status_code
                )
                if _should_skip_page(page):
                    stats.skipped_quality += 1
                    logger.info(
                        "Skipped low-quality page: %s (status=%d title=%r)",
                        fetch_url, page.status_code,
                        page.title[:60] if page.title else "",
                    )
                    return None

                return page

        tasks = [fetch_one(u, d) for u, d in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, PageMetadata):
                prefix = _top_level_prefix(result.url)
                prefix_counts[prefix] += 1
                pages.append(result)
            elif isinstance(result, Exception):
                stats.skipped_errors += 1
                logger.warning("Crawl task exception: %s", result)

    return pages


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def crawl(url: str) -> tuple[list[PageMetadata], str, str, CrawlStats]:
    """Crawl a website starting from *url*.

    Returns (pages, site_title, site_summary, stats).  The homepage is
    fetched first; its links seed a priority-BFS that follows the site's
    own structure to discover important pages.
    """
    parsed_base = urlparse(url)
    base_host = parsed_base.hostname
    if not base_host:
        raise ValueError(f"Cannot determine host from URL: {url}")
    base_host = base_host.lower()

    start_time = time.monotonic()
    stats = CrawlStats()

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        timeout=settings.per_request_timeout,
    ) as client:
        robots = await fetch_robots(url, client)

        homepage, site_title, site_summary, base_host, homepage_links = (
            await _fetch_homepage(url, base_host, client, robots, stats)
        )

        logger.info("Starting BFS crawl with %d homepage links", len(homepage_links))
        pages = await _crawl_bfs(
            url, base_host, client, robots,
            homepage_links, start_time, stats,
        )

        if homepage:
            pages.insert(0, homepage)

    logger.info(
        "Crawl complete: %d pages in %.1fs (fetched=%d) | "
        "skipped: robots=%d errors=%d offsite=%d quality=%d",
        len(pages),
        time.monotonic() - start_time,
        stats.total_fetches,
        stats.skipped_robots,
        stats.skipped_errors,
        stats.skipped_offsite,
        stats.skipped_quality,
    )
    return pages, site_title, site_summary, stats
