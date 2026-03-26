"""Lightweight robots.txt compliance. Best-effort: if parsing fails, allow all."""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from llms_txt_worker.crawler.fetcher import SSRFError, resolve_and_validate, validate_url

logger = logging.getLogger(__name__)

USER_AGENT = "llms-txt-generator"


async def fetch_robots(base_url: str, client: httpx.AsyncClient) -> RobotFileParser:
    """Fetch and parse robots.txt for the given base URL. Returns a permissive parser on failure."""
    parser = RobotFileParser()
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        validate_url(robots_url)
        if parsed.hostname:
            await resolve_and_validate(parsed.hostname)

        response = await client.get(robots_url, follow_redirects=False, timeout=5)
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
            logger.info("Loaded robots.txt from %s", robots_url)
        else:
            parser.allow_all = True
    except SSRFError as exc:
        logger.debug("SSRF blocked for robots.txt %s: %s", robots_url, exc)
        parser.allow_all = True
    except Exception:
        logger.debug("Failed to fetch robots.txt from %s, allowing all", robots_url)
        parser.allow_all = True

    return parser


def is_allowed(parser: RobotFileParser, url: str) -> bool:
    return parser.can_fetch(USER_AGENT, url)
