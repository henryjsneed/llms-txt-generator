"""Generate spec-compliant llms.txt markdown from grouped sections."""

import re

from llms_txt_worker.ranking.grouper import GroupedSection

_SITE_SUFFIX_RE = re.compile(r"\s*[|–—\-]\s*(.+)$")


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

    optional_lines: list[str] = []

    for section in sections:
        if not section.pages:
            continue

        if section.is_optional:
            for page in section.pages:
                if not page.title and not page.description:
                    continue
                entry = _format_entry(page.title, page.url, page.description, site_title)
                optional_lines.append(entry)
            continue

        section_entries: list[str] = []
        for page in section.pages:
            if not page.title and not page.description:
                continue
            section_entries.append(_format_entry(page.title, page.url, page.description, site_title))
        if not section_entries:
            continue
        lines.append(f"## {section.name}")
        lines.append("")
        lines.extend(section_entries)
        lines.append("")

    if optional_lines:
        lines.append("## Optional")
        lines.append("")
        for entry in optional_lines:
            lines.append(entry)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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


def _format_entry(title: str, url: str, description: str, site_title: str) -> str:
    display_title = _strip_site_suffix(title, site_title) if title else url
    if description:
        return f"- [{display_title}]({url}): {description}"
    return f"- [{display_title}]({url})"
