"""Safe HTTP fetcher with SSRF protection.

All URL fetching goes through this module. It resolves DNS before connecting
and rejects any IP in private, loopback, link-local, multicast, or reserved ranges.
"""

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from llms_txt_worker.config import settings

logger = logging.getLogger(__name__)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]

_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_CONTENT_TYPES = {"text/html", "text/xml", "application/xml", "application/xhtml+xml"}


class SSRFError(Exception):
    pass


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return any(addr in network for network in _BLOCKED_NETWORKS)


def validate_url(url: str) -> None:
    """Validate a URL for SSRF safety (scheme and hostname checks only, no DNS)."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"Blocked scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise SSRFError("Missing hostname")

    hostname = parsed.hostname.lower()

    # Catch bare IPs passed directly
    try:
        addr = ipaddress.ip_address(hostname)
        if _is_blocked_ip(str(addr)):
            raise SSRFError(f"Blocked IP: {hostname}")
    except ValueError:
        pass  # Not an IP literal -- hostname will be resolved later in safe_fetch


async def resolve_and_validate(hostname: str) -> list[str]:
    """Resolve hostname to IPs and validate none are in blocked ranges."""
    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(hostname, None, family=socket.AF_UNSPEC)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname}: {exc}") from exc

    ips = list({info[4][0] for info in addrinfo})
    if not ips:
        raise SSRFError(f"No DNS results for {hostname}")

    for ip_str in ips:
        if _is_blocked_ip(ip_str):
            raise SSRFError(f"Resolved to blocked IP: {ip_str}")

    return ips


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    body: str


async def safe_fetch(url: str, client: httpx.AsyncClient) -> FetchResult:
    """Fetch a URL safely with SSRF protection and size/content-type limits."""
    validate_url(url)

    parsed = urlparse(url)
    if not parsed.hostname:
        raise SSRFError("Missing hostname")
    await resolve_and_validate(parsed.hostname)

    response = await client.get(
        url,
        follow_redirects=False,
        timeout=settings.per_request_timeout,
    )

    # Handle redirects manually to validate each hop
    redirect_count = 0
    while response.is_redirect and redirect_count < 5:
        redirect_count += 1
        redirect_url = str(response.next_request.url) if response.next_request else None
        if not redirect_url:
            break

        validate_url(redirect_url)
        redirect_parsed = urlparse(redirect_url)
        if redirect_parsed.hostname:
            await resolve_and_validate(redirect_parsed.hostname)

        response = await client.get(
            redirect_url,
            follow_redirects=False,
            timeout=settings.per_request_timeout,
        )

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise SSRFError(f"Blocked content-type: {content_type}")

    try:
        content_length = int(response.headers.get("content-length", 0))
    except (ValueError, TypeError):
        content_length = 0
    if content_length > settings.max_response_size:
        raise SSRFError(f"Response too large: {content_length} bytes")

    body = response.text
    if len(body.encode("utf-8", errors="replace")) > settings.max_response_size:
        raise SSRFError("Response body exceeds size limit")

    return FetchResult(
        url=str(response.url),
        status_code=response.status_code,
        content_type=content_type,
        body=body,
    )
