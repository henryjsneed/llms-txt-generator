"""Page grouping and ranking for llms.txt section assignment.

Groups pages into named sections using URL-path heuristics and title keyword
fallback. Sections are ordered by a fixed priority, with small dynamically-created
sections and the catch-all "Other" section folded into Optional.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from llms_txt_worker.extraction.parser import canonicalize_url
from llms_txt_worker.persistence.models import PageMetadata

_PATH_RULES: list[tuple[list[str], str]] = [
    (["/docs", "/documentation"], "Documentation"),
    (["/api", "/reference"], "API Reference"),
    (["/guide", "/guides", "/tutorial", "/tutorials", "/getting-started", "/quickstart"], "Guides"),
    (["/example", "/examples", "/sample", "/samples", "/demo", "/demos"], "Examples"),
    (["/blog", "/blogs", "/post", "/posts", "/news", "/article", "/articles", "/changelog"], "Blog"),
    (["/about", "/team", "/company", "/careers"], "About"),
    (["/faq", "/help", "/support", "/contact"], "Support"),
    (["/pricing", "/plan"], "Pricing"),
]

_TITLE_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdocumentation\b"), "Documentation"),
    (re.compile(r"\bdocs\b"), "Documentation"),
    (re.compile(r"\bapi reference\b"), "API Reference"),
    (re.compile(r"\bguide(?:s)?\b"), "Guides"),
    (re.compile(r"\btutorial(?:s)?\b"), "Guides"),
    (re.compile(r"\bexample(?:s)?\b"), "Examples"),
    (re.compile(r"\bblog\b"), "Blog"),
    (re.compile(r"\babout\b"), "About"),
    (re.compile(r"\bfaq\b"), "Support"),
    (re.compile(r"\bpricing\b"), "Pricing"),
]

SECTION_ORDER = [
    "Documentation",
    "API Reference",
    "Guides",
    "Examples",
    "Blog",
    "About",
    "Support",
    "Pricing",
]

OPTIONAL_SECTIONS = {"Blog"}

_KNOWN_SECTIONS = set(SECTION_ORDER)

_TITLE_SEPARATORS = re.compile(r"\s*[|–—]\s*")
_TITLE_KEYWORD_BLOCKLIST_PREFIXES = ("/marketplace",)

MIN_PAGES_FOR_PROMOTED_SECTION = 2
MAX_PAGES_PER_SECTION = 8
_ARTICLE_LIKE_SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){3,}$")


@dataclass
class GroupedSection:
    name: str
    pages: list[PageMetadata] = field(default_factory=list)
    is_optional: bool = False


def _is_homepage(page: PageMetadata) -> bool:
    """True if the page is the site root (path is / or empty)."""
    return urlparse(page.url).path.rstrip("/") == ""


def _refine_section_name(pages: list[PageMetadata], url_based_name: str) -> str:
    """Derive a properly-cased section name from page titles when possible.

    Matches title segments (split on | / – / —) against the URL-derived name
    to preserve original casing (e.g. "CNN Underscored" instead of
    "Cnn Underscored"). Falls back to the URL-derived name when no confident
    match is found.
    """
    shallowest = min(pages, key=lambda p: (p.depth, p.url))
    if not shallowest.title:
        return url_based_name

    url_key = url_based_name.lower()
    for part in _TITLE_SEPARATORS.split(shallowest.title):
        candidate = part.strip()
        if candidate.lower().replace("-", " ").replace("_", " ") == url_key:
            return candidate

    return url_based_name


def classify_page(page: PageMetadata) -> str:
    """Assign a page to a section name based on URL path and title heuristics."""
    parsed = urlparse(page.url)
    path = parsed.path.lower().rstrip("/")

    for prefixes, section_name in _PATH_RULES:
        for prefix in prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                return section_name

    title_lower = page.title.lower()
    if not any(path == prefix or path.startswith(prefix + "/") for prefix in _TITLE_KEYWORD_BLOCKLIST_PREFIXES):
        for keyword, section_name in _TITLE_KEYWORDS:
            if keyword.search(title_lower):
                return section_name

    segments = [s for s in path.split("/") if s]
    if segments:
        first = segments[0]
        if not re.match(r"^[\d\-]+$", first) and len(first) > 2:
            return first.replace("-", " ").replace("_", " ").title()

    return "Other"


def _page_sort_key(page: PageMetadata) -> tuple[int, int, int, str]:
    """Rank structural hub pages ahead of deep or article-like leaf pages."""
    parsed = urlparse(page.url)
    segments = [segment for segment in parsed.path.lower().split("/") if segment]
    last_segment = segments[-1] if segments else ""

    has_query = 1 if parsed.query else 0
    article_like = 1 if _ARTICLE_LIKE_SEGMENT_RE.match(last_segment) else 0
    leaf_penalty = 1 if len(segments) >= 2 and article_like else 0

    return (page.depth + leaf_penalty, article_like, has_query, page.url)


def group_pages(pages: list[PageMetadata]) -> list[GroupedSection]:
    """Group pages into ordered sections for llms.txt output.

    Filters out the homepage (already represented by H1 + blockquote), refines
    section names from page titles, and folds small/unknown sections into Optional.
    """
    filtered = [p for p in pages if not _is_homepage(p)]

    for page in filtered:
        page.url = canonicalize_url(page.url)

    sections: dict[str, GroupedSection] = {}

    for page in filtered:
        section_name = classify_page(page)
        if section_name not in sections:
            sections[section_name] = GroupedSection(
                name=section_name,
                is_optional=section_name in OPTIONAL_SECTIONS,
            )
        sections[section_name].pages.append(page)

    for section in sections.values():
        deduped_pages = list(dict.fromkeys(page.url for page in section.pages))
        by_url = {page.url: page for page in section.pages}
        section.pages = [by_url[url] for url in deduped_pages]

        path_best: dict[str, PageMetadata] = {}
        for page in section.pages:
            parsed = urlparse(page.url)
            path_key = urlunparse(parsed._replace(query="", fragment=""))
            existing = path_best.get(path_key)
            if existing is None or len(page.url) < len(existing.url):
                path_best[path_key] = page
        section.pages = list(path_best.values())

        title_best: dict[str, PageMetadata] = {}
        for page in section.pages:
            key = page.title.strip().lower()
            if not key:
                title_best[page.url] = page
                continue
            existing = title_best.get(key)
            if existing is None or len(page.url) < len(existing.url):
                title_best[key] = page
        section.pages = list(title_best.values())

        section.pages.sort(key=_page_sort_key)
        section.pages = section.pages[:MAX_PAGES_PER_SECTION]

    for key in list(sections):
        if key not in _KNOWN_SECTIONS and key != "Other":
            sections[key].name = _refine_section_name(sections[key].pages, key)

    for key, section in sections.items():
        if section.is_optional:
            continue
        if key == "Other":
            section.is_optional = True
        elif key not in _KNOWN_SECTIONS and len(section.pages) < MIN_PAGES_FOR_PROMOTED_SECTION:
            section.is_optional = True

    ordered: list[GroupedSection] = []
    for name in SECTION_ORDER:
        if name in sections:
            ordered.append(sections.pop(name))

    remaining = sorted(sections.values(), key=lambda s: s.name)
    ordered.extend(remaining)

    return ordered
