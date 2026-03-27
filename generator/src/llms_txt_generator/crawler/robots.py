"""Lightweight robots.txt compliance.

Best-effort: if parsing fails, allow all.
"""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from llms_txt_generator.config import settings
from llms_txt_generator.crawler.fetcher import SSRFError, resolve_and_validate, validate_url

logger = logging.getLogger(__name__)

# wikimedia may reject generic bot user agents so this must be descriptive and contactable
# see https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
USER_AGENT = "llms-txt-generator/1.0 (+https://github.com/henryjsneed/llms-txt-generator)"

async def fetch_robots(
    base_url: str, client: httpx.AsyncClient
) -> RobotFileParser:
    """Fetch and parse robots.txt.

    On failure, returns a permissive parser (allow-all).
    """
    parser = RobotFileParser()
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        validate_url(robots_url)
        if parsed.hostname:
            await resolve_and_validate(parsed.hostname)

        response = await client.get(
            robots_url, follow_redirects=False, timeout=settings.per_request_timeout,
        )
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
            logger.info("Loaded robots.txt from %s", robots_url)
        else:
            logger.info(
                "robots.txt returned status %d from %s, allowing all",
                response.status_code, robots_url,
            )
            parser.allow_all = True
    except SSRFError as exc:
        logger.warning("SSRF blocked for robots.txt %s: %s", robots_url, exc)
        parser.allow_all = True
    except Exception:
        logger.warning("Failed to fetch robots.txt from %s, allowing all", robots_url)
        parser.allow_all = True

    return parser


def is_allowed(parser: RobotFileParser, url: str) -> bool:
    return parser.can_fetch(USER_AGENT, url)
