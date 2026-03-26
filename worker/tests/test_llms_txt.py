import re

import pytest

from llms_txt_worker.generator.llms_txt import generate_llms_txt
from llms_txt_worker.persistence.models import PageMetadata
from llms_txt_worker.ranking.grouper import GroupedSection

# ---------------------------------------------------------------------------
# Spec validator: encodes the structural rules from llmstxt.org so every
# test can assert full compliance, not just spot-check individual features.
# ---------------------------------------------------------------------------

_LIST_ITEM_RE = re.compile(r"^- \[.+?\]\(.+?\)(: .+)?$")


def assert_spec_compliant(text: str) -> None:
    """Validate that *text* conforms to the llms.txt structural spec.

    Rules enforced (derived from https://llmstxt.org/):
      1. Exactly one H1, must be line 1.
      2. Optional blockquote (> ...) immediately after the H1 blank line.
      3. Zero or more H2 sections, each containing a markdown file-list.
      4. Every list item matches ``- [name](url)`` or ``- [name](url): desc``.
      5. No H3+ headers.
      6. ``## Optional`` section, if present, must be the last H2.
      7. File ends with a single trailing newline.
    """
    assert text.endswith("\n"), "File must end with a trailing newline"
    lines = text.rstrip("\n").split("\n")

    # --- Rule 1: exactly one H1, on line 1 ---
    assert lines[0].startswith("# "), "Line 1 must be an H1 (# Title)"
    h1_lines = [i for i, ln in enumerate(lines) if re.match(r"^# ", ln)]
    assert len(h1_lines) == 1, f"Expected exactly 1 H1, found {len(h1_lines)}"

    # --- Rule 5: no H3+ ---
    for i, ln in enumerate(lines):
        assert not re.match(
            r"^#{3,} ", ln
        ), f"Line {i + 1}: H3+ headers are not part of the llms.txt spec"

    # --- Identify structural regions ---
    h2_indices = [i for i, ln in enumerate(lines) if re.match(r"^## ", ln)]

    # --- Rule 2: blockquote must follow H1 (if present) ---
    blockquote_lines = [i for i, ln in enumerate(lines) if ln.startswith("> ")]
    if blockquote_lines:
        first_bq = blockquote_lines[0]
        first_h2 = h2_indices[0] if h2_indices else len(lines)
        assert first_bq < first_h2, "Blockquote must appear before any H2 section"
        assert first_bq <= 2, "Blockquote must follow the H1 (within first 3 lines)"

    # --- Rule 4: every list item in H2 sections must match link format ---
    for idx, h2_idx in enumerate(h2_indices):
        end = h2_indices[idx + 1] if idx + 1 < len(h2_indices) else len(lines)
        for i in range(h2_idx + 1, end):
            ln = lines[i]
            if ln.startswith("- "):
                assert _LIST_ITEM_RE.match(
                    ln
                ), f"Line {i + 1}: list item does not match spec format: {ln!r}"

    # --- Rule 3: each H2 section has at least one list item ---
    for idx, h2_idx in enumerate(h2_indices):
        end = h2_indices[idx + 1] if idx + 1 < len(h2_indices) else len(lines)
        items = [ln for ln in lines[h2_idx + 1 : end] if ln.startswith("- ")]
        section_name = lines[h2_idx]
        assert items, f"{section_name} has no list items"

    # --- Rule 6: ## Optional must be last H2 ---
    optional_indices = [i for i, ln in enumerate(lines) if ln == "## Optional"]
    if optional_indices and h2_indices:
        assert (
            optional_indices[-1] == h2_indices[-1]
        ), "## Optional must be the last H2 section"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSpecCompliance:
    """Structural spec compliance validated by assert_spec_compliant."""

    def test_full_output_with_summary(self):
        sections = [
            GroupedSection(
                name="Documentation",
                pages=[
                    PageMetadata(
                        url="https://ex.com/docs/intro",
                        title="Introduction",
                        description="Get started",
                    ),
                ],
            ),
        ]
        result = generate_llms_txt("My Site", "A great site", sections)
        assert_spec_compliant(result)

    def test_no_summary(self):
        sections = [
            GroupedSection(
                name="Docs",
                pages=[PageMetadata(url="https://ex.com/docs", title="Docs")],
            ),
        ]
        result = generate_llms_txt("My Site", "", sections)
        assert_spec_compliant(result)
        assert ">" not in result

    def test_optional_section_is_last(self):
        sections = [
            GroupedSection(
                name="Documentation",
                pages=[PageMetadata(url="https://ex.com/docs", title="Docs")],
            ),
            GroupedSection(
                name="Blog",
                pages=[PageMetadata(url="https://ex.com/blog/post", title="Post")],
                is_optional=True,
            ),
        ]
        result = generate_llms_txt("Site", "Desc", sections)
        assert_spec_compliant(result)
        assert "## Blog" not in result
        assert "## Optional" in result

    def test_multiple_sections(self):
        sections = [
            GroupedSection(
                name="Documentation",
                pages=[PageMetadata(url="https://ex.com/docs", title="Docs")],
            ),
            GroupedSection(
                name="API Reference",
                pages=[PageMetadata(url="https://ex.com/api", title="API")],
            ),
            GroupedSection(
                name="Guides",
                pages=[
                    PageMetadata(
                        url="https://ex.com/guides/setup",
                        title="Setup Guide",
                        description="Step-by-step",
                    ),
                ],
            ),
        ]
        result = generate_llms_txt("Site", "Description", sections)
        assert_spec_compliant(result)

    def test_mixed_optional_and_required(self):
        sections = [
            GroupedSection(
                name="Docs",
                pages=[PageMetadata(url="https://ex.com/docs", title="Docs")],
            ),
            GroupedSection(
                name="About",
                pages=[PageMetadata(url="https://ex.com/about", title="About")],
            ),
            GroupedSection(
                name="Blog",
                pages=[PageMetadata(url="https://ex.com/blog/a", title="A")],
                is_optional=True,
            ),
            GroupedSection(
                name="Archive",
                pages=[PageMetadata(url="https://ex.com/archive", title="Archive")],
                is_optional=True,
            ),
        ]
        result = generate_llms_txt("Site", "Summary", sections)
        assert_spec_compliant(result)
        lines = result.split("\n")
        h2s = [ln for ln in lines if ln.startswith("## ")]
        assert h2s[-1] == "## Optional"

    def test_entry_format_with_description(self):
        sections = [
            GroupedSection(
                name="Docs",
                pages=[
                    PageMetadata(
                        url="https://ex.com/docs",
                        title="Docs",
                        description="Full reference",
                    ),
                ],
            ),
        ]
        result = generate_llms_txt("S", "", sections)
        assert_spec_compliant(result)
        assert "- [Docs](https://ex.com/docs): Full reference" in result

    def test_entry_format_without_description(self):
        sections = [
            GroupedSection(
                name="About",
                pages=[PageMetadata(url="https://ex.com/about", title="About Us")],
            ),
        ]
        result = generate_llms_txt("S", "", sections)
        assert_spec_compliant(result)
        line = next(ln for ln in result.split("\n") if ln.startswith("- "))
        assert line == "- [About Us](https://ex.com/about)"

    def test_url_fallback_for_missing_title(self):
        sections = [
            GroupedSection(
                name="Other",
                pages=[PageMetadata(url="https://ex.com/page", title="")],
            ),
        ]
        result = generate_llms_txt("S", "", sections)
        assert_spec_compliant(result)
        assert "- [https://ex.com/page](https://ex.com/page)" in result

    def test_only_optional_sections(self):
        sections = [
            GroupedSection(
                name="Blog",
                pages=[PageMetadata(url="https://ex.com/blog", title="Blog")],
                is_optional=True,
            ),
        ]
        result = generate_llms_txt("S", "D", sections)
        assert_spec_compliant(result)

    def test_empty_sections_omitted(self):
        sections = [
            GroupedSection(name="Empty", pages=[]),
            GroupedSection(
                name="Docs",
                pages=[PageMetadata(url="https://ex.com/docs", title="Docs")],
            ),
        ]
        result = generate_llms_txt("S", "", sections)
        assert_spec_compliant(result)
        assert "## Empty" not in result


class TestSpecValidatorCatchesViolations:
    """Verify the validator itself rejects malformed output."""

    def test_rejects_missing_h1(self):
        with pytest.raises(AssertionError, match="H1"):
            assert_spec_compliant("## Section\n\n- [A](https://a.com)\n")

    def test_rejects_multiple_h1(self):
        with pytest.raises(AssertionError, match="H1"):
            assert_spec_compliant(
                "# One\n\n# Two\n\n## S\n\n- [A](https://a.com)\n"
            )

    def test_rejects_h3(self):
        with pytest.raises(AssertionError, match="H3"):
            assert_spec_compliant(
                "# T\n\n### Sub\n\n## S\n\n- [A](https://a.com)\n"
            )

    def test_rejects_malformed_list_item(self):
        with pytest.raises(AssertionError, match="list item"):
            assert_spec_compliant("# T\n\n## S\n\n- just text no link\n")

    def test_rejects_optional_not_last(self):
        with pytest.raises(AssertionError, match="Optional"):
            assert_spec_compliant(
                "# T\n\n## Optional\n\n- [A](https://a.com)\n\n"
                "## Docs\n\n- [B](https://b.com)\n"
            )

    def test_rejects_missing_trailing_newline(self):
        with pytest.raises(AssertionError, match="newline"):
            assert_spec_compliant("# T\n\n## S\n\n- [A](https://a.com)")

    def test_rejects_empty_section(self):
        with pytest.raises(AssertionError, match="no list items"):
            assert_spec_compliant("# T\n\n## Empty\n\n## Docs\n\n- [A](https://a.com)\n")
