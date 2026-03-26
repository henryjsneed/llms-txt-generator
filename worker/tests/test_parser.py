from llms_txt_worker.extraction.parser import (
    extract_internal_links,
    extract_metadata,
    extract_site_info,
)


def _html(
    title: str = "Test Page",
    description: str = "A test page",
    body: str = "<p>Hello</p>",
    og_site_name: str | None = None,
) -> str:
    og = ""
    if og_site_name:
        og = f'<meta property="og:site_name" content="{og_site_name}"/>'
    return f"""
    <html>
    <head>
        <title>{title}</title>
        <meta name="description" content="{description}"/>
        {og}
    </head>
    <body>{body}</body>
    </html>
    """


class TestExtractMetadata:
    def test_extracts_title(self):
        page = extract_metadata("https://example.com", _html(title="My Page"), 0, 200)
        assert page.title == "My Page"

    def test_extracts_description(self):
        page = extract_metadata("https://example.com", _html(description="Cool site"), 0, 200)
        assert page.description == "Cool site"

    def test_preserves_url_and_depth(self):
        page = extract_metadata("https://example.com/docs", _html(), 2, 200)
        assert page.url == "https://example.com/docs"
        assert page.depth == 2
        assert page.status_code == 200

    def test_empty_html(self):
        page = extract_metadata("https://example.com", "", 0, 200)
        assert page.title == ""
        assert page.description == ""


class TestExtractInternalLinks:
    def test_same_origin_links(self):
        html = '<a href="/docs">Docs</a><a href="/blog">Blog</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert "https://example.com/docs" in links
        assert "https://example.com/blog" in links

    def test_filters_external(self):
        html = '<a href="https://other.com/page">External</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert len(links) == 0

    def test_skips_mailto_and_tel(self):
        html = '<a href="mailto:x@y.com">Email</a><a href="tel:123">Call</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert len(links) == 0

    def test_skips_fragment_only(self):
        html = '<a href="#section">Jump</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert len(links) == 0

    def test_deduplicates(self):
        html = '<a href="/docs">A</a><a href="/docs">B</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert links.count("https://example.com/docs") == 1

    def test_resolves_relative(self):
        html = '<a href="page2">Next</a>'
        links = extract_internal_links(html, "https://example.com/docs/", "example.com")
        assert "https://example.com/docs/page2" in links

    def test_strips_tracking_query_params(self):
        html = '<a href="/subscribe?source=footer&utm_campaign=spring&id=42">Subscribe</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert "https://example.com/subscribe?id=42" in links

    def test_strips_ref_underscore_param(self):
        html = (
            '<a href="/prime?ref_=nav_cs_primelink">A</a>'
            '<a href="/prime?ref_=footer_link">B</a>'
        )
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert links == ["https://example.com/prime"]

    def test_strips_ie_and_theme_params(self):
        html = '<a href="/category?ie=UTF8&node=123&theme=light">Cat</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert links == ["https://example.com/category?node=123"]

    def test_normalizes_trailing_slashes(self):
        html = '<a href="/docs/">A</a><a href="/docs">B</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert links == ["https://example.com/docs"]

    def test_deduplicates_tracking_variants(self):
        html = (
            '<a href="/games/play/daily-crossword?utm_source=home">A</a>'
            '<a href="/games/play/daily-crossword?source=footer">B</a>'
        )
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert links == ["https://example.com/games/play/daily-crossword"]

    def test_strips_from_param(self):
        html = '<a href="/careers/job-123?from=careers">Apply</a>'
        links = extract_internal_links(html, "https://example.com", "example.com")
        assert links == ["https://example.com/careers/job-123"]


class TestExtractSiteInfo:
    def test_uses_og_site_name(self):
        html = _html(title="Page Title", og_site_name="My Site")
        title, desc = extract_site_info(html)
        assert title == "My Site"

    def test_falls_back_to_title(self):
        html = _html(title="My Site - Home")
        title, desc = extract_site_info(html)
        assert title == "My Site - Home"

    def test_extracts_description(self):
        html = _html(description="Welcome to my site")
        _, desc = extract_site_info(html)
        assert desc == "Welcome to my site"
