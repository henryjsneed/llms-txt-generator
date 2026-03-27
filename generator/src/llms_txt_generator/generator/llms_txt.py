"""Generate spec-compliant llms.txt markdown from grouped sections."""

import re
from collections import Counter

from llms_txt_generator.ranking.grouper import GroupedSection

_SITE_SUFFIX_RE = re.compile(r"\s*[|–—\-]\s*(.+)$")
_SENTENCE_END_RE = re.compile(r"(?<=[a-z]{2}[.!?])\s+(?=[A-Z])")
MAX_DESCRIPTION_LENGTH = 200
BOILERPLATE_THRESHOLD = 3


def generate_llms_txt(
    site_title: str,
    site_summary: str,
    sections: list[GroupedSection],
) -> str:
    """Produce a spec-compliant llms.txt string.

    Format per llmstxt.org:
      # Title
      > Description
      ## Section
      - [Link title](url): Optional description
      ## Optional
      - [Link title](url)
    """
    lines: list[str] = []

    lines.append(f"# {site_title}")
    lines.append("")

    if site_summary:
        lines.append(f"> {site_summary}")
        lines.append("")

    boilerplate = _detect_boilerplate(sections, site_summary)
    optional_lines: list[str] = []

    for section in sections:
        if not section.pages:
            continue

        if section.is_optional:
            for page in section.pages:
                if not page.title:
                    continue
                entry = _format_entry(page.title, page.url, page.description, site_title, boilerplate)
                optional_lines.append(entry)
            continue

        section_entries: list[str] = []
        for page in section.pages:
            if not page.title:
                continue
            section_entries.append(_format_entry(page.title, page.url, page.description, site_title, boilerplate))
        if not section_entries:
            continue
        lines.append(f"## {section.name}")
        lines.append("")
        lines.extend(section_entries)
        lines.append("")

    if optional_lines:
        lines.append("## Optional")
        lines.append("")
        lines.extend(optional_lines)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


BOILERPLATE_PREFIX_LEN = 40


def _detect_boilerplate(sections: list[GroupedSection], site_summary: str) -> frozenset[str]:
    """Identify descriptions repeated across many pages (site-wide defaults).

    Catches both exact duplicates and template variations where descriptions
    share a long common prefix (e.g. "X is your trusted source for the latest
    {beauty,fashion,home} trends, how-to's, and product reviews.").
    """
    desc_counts: Counter[str] = Counter()
    prefix_groups: dict[str, set[str]] = {}
    for section in sections:
        for page in section.pages:
            if not page.description:
                continue
            desc_counts[page.description] += 1
            if len(page.description) >= BOILERPLATE_PREFIX_LEN:
                prefix = page.description[:BOILERPLATE_PREFIX_LEN]
                prefix_groups.setdefault(prefix, set()).add(page.description)

    result: set[str] = set()
    for desc, count in desc_counts.items():
        if count >= BOILERPLATE_THRESHOLD:
            result.add(desc)
    for descs in prefix_groups.values():
        if len(descs) >= BOILERPLATE_THRESHOLD:
            result.update(descs)
    if site_summary:
        result.add(site_summary)
    return frozenset(result)


def _strip_site_suffix(title: str, site_title: str) -> str:
    """Remove trailing '| SiteName' or '- SiteName' when it matches the H1."""
    m = _SITE_SUFFIX_RE.search(title)
    if not m:
        return title
    suffix = m.group(1).strip()
    if suffix.lower() == site_title.lower() or site_title.lower().startswith(suffix.lower()):
        stripped = title[: m.start()].strip()
        return stripped if stripped else title
    return title


_SITE_PREFIX_RE = re.compile(r"^(.+?):\s+")


def _strip_site_prefix(title: str, site_title: str) -> str:
    """Remove leading 'SiteName: ' when it matches the H1."""
    m = _SITE_PREFIX_RE.match(title)
    if not m:
        return title
    prefix = m.group(1).strip()
    if prefix.lower() == site_title.lower() or site_title.lower().startswith(prefix.lower()):
        stripped = title[m.end():].strip()
        return stripped if stripped else title
    return title


def _clean_title(title: str, site_title: str) -> str:
    """Strip both site-name prefix and suffix from a page title."""
    cleaned = _strip_site_prefix(title, site_title)
    cleaned = _strip_site_suffix(cleaned, site_title)
    return cleaned


def _truncate_description(text: str, max_len: int = MAX_DESCRIPTION_LENGTH) -> str:
    """Truncate at a sentence boundary near *max_len*, with word-break fallback."""
    if len(text) <= max_len:
        return text
    sentences = _SENTENCE_END_RE.split(text)
    if sentences and len(sentences[0]) <= max_len:
        result = ""
        for sentence in sentences:
            candidate = f"{result} {sentence}".strip() if result else sentence
            if len(candidate) > max_len:
                break
            result = candidate
        if result:
            return result
    truncated = text[:max_len].rsplit(" ", 1)[0]
    return truncated + "\u2026"


def _format_entry(
    title: str,
    url: str,
    description: str,
    site_title: str,
    boilerplate: frozenset[str] = frozenset(),
) -> str:
    display_title = _clean_title(title, site_title) if title else url
    if description and description not in boilerplate:
        return f"- [{display_title}]({url}): {_truncate_description(description)}"
    return f"- [{display_title}]({url})"
