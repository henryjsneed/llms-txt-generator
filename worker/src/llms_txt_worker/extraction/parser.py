"""HTML metadata extraction using BeautifulSoup."""

from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from llms_txt_worker.persistence.models import PageMetadata

# Non-content-differentiating query parameters stripped during URL
# canonicalization.  Sourced from chrome-utm-stripper
# (github.com/jparise/chrome-utm-stripper) and ClearURLs, plus
# common site-specific params observed in the wild.
#
# Families like utm_*, stm_*, and pf_rd_* are also caught by a
# startswith() check in canonicalize_url.
_TRACKING_QUERY_KEYS: frozenset[str] = frozenset({
    # Google Analytics / Ads
    "_ga",
    "gclid",
    "gclsrc",
    # Meta (Facebook / Instagram)
    "fbclid",
    "igshid",
    # Microsoft / Bing
    "msclkid",
    "cvid",
    "oicd",
    # Twitter / X
    "twclid",
    # LinkedIn
    "li_fat_id",
    # Yandex
    "yclid",
    "_openstat",
    # HubSpot
    "_hsenc",
    "_hsmi",
    # Mailchimp
    "mc_cid",
    "mc_eid",
    # Marketo
    "mkt_tok",
    # Pinterest
    "epik",
    # Adobe Analytics
    "s_cid",
    "sc_cid",
    # Olytics
    "oly_anon_id",
    "oly_enc_id",
    "otc",
    # Yahoo
    "soc_src",
    "soc_trk",
    # ActiveCampaign
    "vgo_ee",
    # Other cross-site trackers
    "icid",
    "rb_clickid",
    "wickedid",
    # Generic referral / attribution
    "ref",
    "ref_",
    "ref_src",
    "referrer",
    "source",
    "src",
    "iid",
    # Amazon-specific non-content params
    "_encoding",
    "ie",
    "navStore",
    "pageId",
    "plattr",
    # Display preferences (not content-differentiating)
    "theme",
})

_TRACKING_QUERY_PREFIXES = ("utm_", "stm_", "pf_rd_", "pd_rd_")


def extract_metadata(url: str, html: str, depth: int, status_code: int) -> PageMetadata:
    """Extract title, description, and other metadata from an HTML page."""
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup)
    description = _extract_description(soup)

    return PageMetadata(
        url=url,
        title=title,
        description=description,
        depth=depth,
        status_code=status_code,
    )


def extract_internal_links(html: str, page_url: str, base_host: str) -> list[str]:
    """Extract same-origin internal links from HTML."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)

        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.hostname and parsed.hostname.lower() != base_host:
            continue

        clean = canonicalize_url(absolute)

        links.append(clean)

    return list(dict.fromkeys(links))


def canonicalize_url(url: str) -> str:
    """Normalize a URL by stripping tracking params, fragments, and trailing slashes."""
    parsed = urlparse(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
        and not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    path = unquote(parsed.path)
    path = path.rstrip("/") or "/"
    return parsed._replace(
        path=path,
        query=urlencode(filtered_query, doseq=True),
        fragment="",
    ).geturl()


def extract_site_info(html: str) -> tuple[str, str]:
    """Extract site name and description from homepage HTML."""
    soup = BeautifulSoup(html, "lxml")
    title = _extract_site_name(soup)
    description = _extract_description(soup)
    return title, description


def _extract_title(soup: BeautifulSoup) -> str:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()

    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    return ""


def _extract_site_name(soup: BeautifulSoup) -> str:
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        return og_site["content"].strip()

    return _extract_title(soup)


def _extract_description(soup: BeautifulSoup) -> str:
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        return og_desc["content"].strip()

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"].strip()

    return ""
