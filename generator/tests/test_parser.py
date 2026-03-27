from llms_txt_generator.extraction.parser import (
    canonicalize_url,
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
        title, _ = extract_site_info(html)
        assert title == "My Site"

    def test_strips_tagline_from_domain_title(self):
        html = _html(title="Amazon.com. Spend less. Smile more.")
        title, _ = extract_site_info(html)
        assert title == "Amazon.com"

    def test_preserves_plain_domain_title(self):
        html = _html(title="Amazon.com")
        title, _ = extract_site_info(html)
        assert title == "Amazon.com"

    def test_strips_pipe_tagline(self):
        html = _html(title="CNN | Breaking News")
        title, _ = extract_site_info(html)
        assert title == "CNN"

    def test_uses_meta_description(self):
        html = _html(description="Welcome to my site, a place for great documentation and resources")
        _, desc = extract_site_info(html)
        assert desc == "Welcome to my site, a place for great documentation and resources"

    def test_falls_back_to_body_when_no_meta_description(self):
        html = """
        <html><head><title>Acme</title></head>
        <body><main>
          <p>Acme Corp builds developer tools for modern cloud infrastructure.</p>
        </main></body></html>
        """
        _, desc = extract_site_info(html)
        assert "Acme Corp" in desc

    def test_prefers_jsonld_over_meta_description(self):
        html = """
        <html><head>
          <title>Wendy's</title>
          <meta name="description" content="Score the Wendy's you love anytime online!"/>
          <script type="application/ld+json">
            {"@type": "Organization", "name": "Wendy's",
             "description": "Wendy's is an international fast food restaurant chain founded by Dave Thomas."}
          </script>
        </head><body></body></html>
        """
        _, desc = extract_site_info(html)
        assert "fast food restaurant" in desc

    def test_prefers_jsonld_over_body_paragraph(self):
        html = """
        <html><head>
          <title>Acme</title>
          <script type="application/ld+json">
            {"@type": "Corporation", "name": "Acme",
             "description": "Acme Corp is a global leader in cloud infrastructure."}
          </script>
        </head><body><main><p>This week only: 50% off all plans! Sign up now to save big.</p></main></body></html>
        """
        _, desc = extract_site_info(html)
        assert "global leader" in desc

    def test_handles_jsonld_graph_wrapper(self):
        html = """
        <html><head>
          <title>Acme</title>
          <script type="application/ld+json">
            {"@context": "https://schema.org", "@graph": [
              {"@type": "WebSite", "name": "Acme", "description": "Acme provides enterprise cloud solutions for modern teams."},
              {"@type": "BreadcrumbList"}
            ]}
          </script>
        </head><body></body></html>
        """
        _, desc = extract_site_info(html)
        assert "enterprise cloud" in desc

    def test_ignores_jsonld_without_description(self):
        html = """
        <html><head>
          <title>Acme</title>
          <meta name="description" content="A good meta description for Acme Corp that should be used."/>
          <script type="application/ld+json">
            {"@type": "Organization", "name": "Acme", "url": "https://acme.com"}
          </script>
        </head><body></body></html>
        """
        _, desc = extract_site_info(html)
        assert "good meta description" in desc

    def test_ignores_short_jsonld_description(self):
        html = """
        <html><head>
          <title>Acme</title>
          <meta name="description" content="Acme Corp builds reliable cloud infrastructure for developers worldwide."/>
          <script type="application/ld+json">
            {"@type": "Organization", "name": "Acme", "description": "Welcome!"}
          </script>
        </head><body></body></html>
        """
        _, desc = extract_site_info(html)
        assert "reliable cloud" in desc

    def test_uses_any_meta_description(self):
        html = _html(
            description="Score the Wendy's you love anytime online! We're just an easy click away.",
        )
        _, desc = extract_site_info(html)
        assert "Wendy's" in desc

    def test_uses_ecommerce_description(self):
        html = _html(
            description=(
                "Free shipping on millions of items. Get the best of Shopping and "
                "Entertainment with Prime."
            ),
        )
        _, desc = extract_site_info(html)
        assert "Free shipping" in desc

    def test_jsonld_localbusiness_type(self):
        html = """
        <html><head>
          <title>Joe's Pizza</title>
          <script type="application/ld+json">
            {"@type": "LocalBusiness", "name": "Joe's Pizza",
             "description": "Joe's Pizza has been serving authentic New York-style pizza since 1975."}
          </script>
        </head><body></body></html>
        """
        _, desc = extract_site_info(html)
        assert "authentic New York-style pizza" in desc


class TestCanonicalizeUrl:
    def test_strips_tracking_params(self):
        assert canonicalize_url("https://ex.com/page?utm_source=home&id=1") == "https://ex.com/page?id=1"

    def test_strips_fragment(self):
        assert canonicalize_url("https://ex.com/docs#section") == "https://ex.com/docs"

    def test_strips_trailing_slash(self):
        assert canonicalize_url("https://ex.com/docs/") == "https://ex.com/docs"

    def test_preserves_root_slash(self):
        assert canonicalize_url("https://ex.com/") == "https://ex.com/"

    def test_strips_prefix_family_params(self):
        assert canonicalize_url("https://ex.com/p?pf_rd_p=abc&stm_id=1") == "https://ex.com/p"

    def test_decodes_percent_encoded_path(self):
        assert canonicalize_url("https://ex.com/caf%C3%A9") == "https://ex.com/café"

    def test_preserves_content_params(self):
        assert canonicalize_url("https://ex.com/search?q=test&page=2") == "https://ex.com/search?q=test&page=2"

    def test_url_with_only_tracking_params(self):
        assert canonicalize_url("https://ex.com/page?fbclid=abc&gclid=def") == "https://ex.com/page"
