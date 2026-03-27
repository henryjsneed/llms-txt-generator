"""Page grouping and ranking for llms.txt section assignment.

Groups pages into named sections derived purely from URL structure.
The first path segment determines the section name — pages at
/docs/intro and /docs/advanced both land in "Docs".

Promoted sections are ordered by page count (descending). Small
sections fold into Optional.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from llms_txt_generator.extraction.parser import canonicalize_url
from llms_txt_generator.persistence.models import PageMetadata

_TITLE_SEPARATORS = re.compile(r"\s*[|–—]\s*")

_OPTIONAL_PATH_PREFIXES = frozenset({
    "/account", "/login", "/signin", "/signup", "/register",
    "/settings", "/terms", "/legal", "/privacy", "/cookie",
})

_DEMOTED_SECTION_PREFIXES = frozenset({
    "/profiles", "/people", "/staff", "/contributors", "/authors",
})
_DEMOTED_SECTION_MAX_PAGES = 3

MAX_PAGES_PER_SECTION = 8
MIN_PAGES_FOR_PROMOTED_SECTION = 2
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

    Tries exact match first, then looks for the URL-derived name as a
    contiguous word sequence within title segments (e.g. "firetv" matches
    "Amazon Fire TV Home" → "Fire TV").  Falls back to the URL-derived name.
    """
    shallowest = min(pages, key=lambda p: (p.depth, p.url))
    if not shallowest.title:
        return url_based_name

    url_key = url_based_name.lower().replace(" ", "")

    for part in _TITLE_SEPARATORS.split(shallowest.title):
        candidate = part.strip()
        normalized = candidate.lower().replace("-", " ").replace("_", " ")
        if normalized == url_key.replace("-", " ").replace("_", " "):
            return candidate

    for page in sorted(pages, key=lambda p: (p.depth, p.url)):
        if not page.title:
            continue
        for part in _TITLE_SEPARATORS.split(page.title):
            match = _find_contiguous_match(part.strip(), url_key)
            if match:
                return match

    return url_based_name


def _find_contiguous_match(title_segment: str, url_key: str) -> str | None:
    """Find a contiguous word sequence in *title_segment* whose letters
    (ignoring spaces) equal *url_key*.  Returns the matched words with
    original casing, or None."""
    words = title_segment.split()
    for start in range(len(words)):
        combined = ""
        for end in range(start, len(words)):
            combined += words[end].lower()
            if combined == url_key:
                return " ".join(words[start : end + 1])
            if len(combined) > len(url_key):
                break
    return None


def classify_page(page: PageMetadata) -> str:
    """Assign a page to a section based on the first URL path segment.

    No lookup tables or keyword matching — the URL structure alone
    determines the section. Short segments (≤2 chars) like /gp or /dp
    are too opaque to be useful section names and fall through to Other.
    """
    parsed = urlparse(page.url)
    path = parsed.path.lower().rstrip("/")

    segments = [s for s in path.split("/") if s]
    if segments:
        first = segments[0]
        if not re.match(r"^[\d\-]+$", first) and len(first) > 2:
            return first.replace("-", " ").replace("_", " ").title()

    return "Other"


def _page_sort_key(page: PageMetadata) -> tuple[int, int, int, int, str]:
    """Rank structural hub pages ahead of deep or article-like leaf pages.

    Pages with descriptions sort before pages without at the same depth,
    so richer entries survive per-section caps.
    """
    parsed = urlparse(page.url)
    segments = [segment for segment in parsed.path.lower().split("/") if segment]
    last_segment = segments[-1] if segments else ""

    has_query = 1 if parsed.query else 0
    article_like = 1 if _ARTICLE_LIKE_SEGMENT_RE.match(last_segment) else 0
    leaf_penalty = 1 if len(segments) >= 2 and article_like else 0
    no_description = 0 if page.description else 1

    return (page.depth + leaf_penalty, no_description, article_like, has_query, page.url)


def _to_url_key(section_key: str) -> str:
    """Convert a title-cased section key back to URL segment form."""
    return section_key.lower().replace(" ", "-")


def _merge_child_sections(sections: dict[str, GroupedSection]) -> None:
    """Merge child sections into established parent sections.

    If section "Iphone" exists (from crawling /iphone) and "Iphone 17 Pro"
    also exists (from /iphone-17-pro), merge the latter into the former.
    The dash-prefix relationship means the child path is structurally
    subordinate to the parent.

    Only merges into parents that already exist as sections — no parents
    are invented.  This keeps grouping grounded in the site's actual
    URL structure rather than any hardcoded product knowledge.
    """
    keys_by_len = sorted(sections, key=lambda k: len(k))
    merge_map: dict[str, str] = {}

    for i, child_key in enumerate(keys_by_len):
        if child_key in merge_map:
            continue
        child_url = _to_url_key(child_key)
        for parent_key in keys_by_len[:i]:
            if parent_key in merge_map:
                continue
            parent_url = _to_url_key(parent_key)
            if child_url.startswith(parent_url + "-"):
                merge_map[child_key] = parent_key
                break

    for child_key, parent_key in merge_map.items():
        sections[parent_key].pages.extend(sections[child_key].pages)
        del sections[child_key]


def group_pages(pages: list[PageMetadata]) -> list[GroupedSection]:
    """Group pages into ordered sections for llms.txt output.

    Filters out the homepage (already represented by H1 + blockquote),
    merges child sections into parent sections based on URL prefix
    relationships, refines section names from page titles, and folds
    small/unknown sections into Optional.
    """
    filtered = [
        p.model_copy(update={"url": canonicalize_url(p.url)})
        for p in pages
        if not _is_homepage(p)
    ]

    sections: dict[str, GroupedSection] = {}

    for page in filtered:
        section_name = classify_page(page)
        if section_name not in sections:
            sections[section_name] = GroupedSection(name=section_name)
        sections[section_name].pages.append(page)

    _merge_child_sections(sections)

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
        if key != "Other":
            sections[key].name = _refine_section_name(sections[key].pages, key)

    for key, section in sections.items():
        if section.is_optional:
            continue
        if key == "Other":
            section.is_optional = True
            continue
        segments = urlparse(section.pages[0].url).path.lower().split("/") if section.pages else []
        first_segment = "/" + segments[1] if len(segments) > 1 and segments[1] else ""
        if first_segment in _OPTIONAL_PATH_PREFIXES:
            section.is_optional = True
        elif first_segment in _DEMOTED_SECTION_PREFIXES:
            section.is_optional = True
            section.pages = section.pages[:_DEMOTED_SECTION_MAX_PAGES]
        elif len(section.pages) < MIN_PAGES_FOR_PROMOTED_SECTION:
            section.is_optional = True

    promoted = sorted(
        [s for s in sections.values() if not s.is_optional],
        key=lambda s: (-len(s.pages), s.name),
    )
    optional = sorted(
        [s for s in sections.values() if s.is_optional],
        key=lambda s: s.name,
    )
    return promoted + optional
