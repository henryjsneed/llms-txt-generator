"""HTML metadata extraction using BeautifulSoup."""

import json
import re
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from llms_txt_generator.persistence.models import PageMetadata

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
    "from",
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
    """Extract site name and description from homepage HTML.

    Priority order for the description:
      1. Schema.org JSON-LD (Organization / WebSite / Corporation)
      2. Meta description (og:description / <meta name="description">)
      3. First substantial body paragraph
      4. Empty string (the blockquote is optional per spec)
    """
    soup = BeautifulSoup(html, "lxml")
    title = _extract_site_name(soup)

    for candidate in (
        _extract_jsonld_description(soup),
        _extract_description(soup),
        _extract_body_summary(soup),
    ):
        if candidate:
            return title, candidate

    return title, ""


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


_TITLE_SEPARATOR_RE = re.compile(r"\s*[|–—\-]\s+.+$")
_TITLE_DOMAIN_TAGLINE_RE = re.compile(
    r"^(.+?\.(?:com|org|net|io|co|ai|edu|gov|us|uk|de|fr|jp))\.\s+.+$",
    re.IGNORECASE,
)


def _clean_site_name(raw: str) -> str:
    """Strip taglines from site names.

    Handles 'Amazon.com. Spend less. Smile more.' → 'Amazon.com'
    and 'My Site | Tagline' → 'My Site'.
    """
    m = _TITLE_SEPARATOR_RE.search(raw)
    if m:
        cleaned = raw[: m.start()].strip()
        if cleaned:
            raw = cleaned

    m = _TITLE_DOMAIN_TAGLINE_RE.match(raw)
    if m:
        return m.group(1)

    return raw


def _extract_site_name(soup: BeautifulSoup) -> str:
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        return _clean_site_name(og_site["content"].strip())

    return _clean_site_name(_extract_title(soup))


def _extract_description(soup: BeautifulSoup) -> str:
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        return _clean_description(og_desc["content"].strip())

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        return _clean_description(meta_desc["content"].strip())

    return ""


def _extract_jsonld_description(soup: BeautifulSoup) -> str:
    """Extract a description from Schema.org JSON-LD embedded in the page.

    Accepts any JSON-LD object with a description field of sufficient
    length.  This function only runs on the homepage, where JSON-LD
    descriptions are almost always site-relevant.  The 30-char minimum
    filters trivial values like "Welcome!" or "Home".
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if "@graph" in item:
                graph = item["@graph"]
                if isinstance(graph, list):
                    candidates.extend(graph)
                continue
            desc = item.get("description", "")
            if isinstance(desc, str) and len(desc) >= 30:
                return _clean_description(desc[:300])
    return ""


def _extract_body_summary(soup: BeautifulSoup, min_length: int = 50) -> str:
    """Extract the first substantial paragraph from the page body."""
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return ""
    for p in main.find_all("p", recursive=True):
        text = p.get_text(separator=" ", strip=True)
        if len(text) >= min_length:
            return _clean_description(text[:300])
    return ""


def _clean_description(text: str) -> str:
    """Strip residual HTML tags and collapse whitespace in descriptions."""
    if "<" in text and ">" in text:
        cleaned = BeautifulSoup(text, "lxml").get_text(separator=" ")
        return " ".join(cleaned.split())
    return " ".join(text.split())
