"""Generate spec-compliant llms.txt markdown from grouped sections."""

from llms_txt_worker.ranking.grouper import GroupedSection


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
                entry = _format_entry(page.title, page.url, page.description)
                optional_lines.append(entry)
            continue

        lines.append(f"## {section.name}")
        lines.append("")
        for page in section.pages:
            lines.append(_format_entry(page.title, page.url, page.description))
        lines.append("")

    if optional_lines:
        lines.append("## Optional")
        lines.append("")
        for entry in optional_lines:
            lines.append(entry)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_entry(title: str, url: str, description: str) -> str:
    display_title = title or url
    if description:
        return f"- [{display_title}]({url}): {description}"
    return f"- [{display_title}]({url})"
