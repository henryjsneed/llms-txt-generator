from llms_txt_worker.persistence.models import PageMetadata
from llms_txt_worker.ranking.grouper import classify_page, group_pages


def _page(url: str, title: str = "", depth: int = 0) -> PageMetadata:
    return PageMetadata(url=url, title=title, depth=depth)


class TestClassifyPage:
    def test_docs_path(self):
        assert classify_page(_page("https://ex.com/docs/intro")) == "Documentation"
        assert classify_page(_page("https://ex.com/documentation/api")) == "Documentation"

    def test_api_path(self):
        assert classify_page(_page("https://ex.com/api/v1")) == "API Reference"
        assert classify_page(_page("https://ex.com/reference/endpoints")) == "API Reference"

    def test_blog_path(self):
        assert classify_page(_page("https://ex.com/blog/my-post")) == "Blog"
        assert classify_page(_page("https://ex.com/news/update")) == "Blog"

    def test_guides_path(self):
        assert classify_page(_page("https://ex.com/guides/setup")) == "Guides"
        assert classify_page(_page("https://ex.com/tutorials/basics")) == "Guides"

    def test_about_path(self):
        assert classify_page(_page("https://ex.com/about")) == "About"
        assert classify_page(_page("https://ex.com/team")) == "About"

    def test_title_keyword_fallback(self):
        page = _page("https://ex.com/something", title="Getting Started Guide")
        assert classify_page(page) == "Guides"

    def test_title_keyword_uses_word_boundaries(self):
        page = _page(
            "https://ex.com/politics/story",
            title="Deal to reopen DHS sputters on Capitol Hill",
        )
        assert classify_page(page) == "Politics"

    def test_marketplace_path_beats_docs_title(self):
        page = _page(
            "https://ex.com/marketplace/commands/docs",
            title="docs | Cursor Command",
        )
        assert classify_page(page) == "Marketplace"

    def test_first_path_segment_fallback(self):
        page = _page("https://ex.com/products/widget")
        assert classify_page(page) == "Products"

    def test_short_path_segment_falls_to_other(self):
        assert classify_page(_page("https://ex.com/dp/B07984JN3L")) == "Other"
        assert classify_page(_page("https://ex.com/gp/browse")) == "Other"
        assert classify_page(_page("https://ex.com/ap/signin")) == "Other"
        assert classify_page(_page("https://ex.com/b/node123")) == "Other"

    def test_root_returns_other(self):
        page = _page("https://ex.com/")
        assert classify_page(page) == "Other"


class TestGroupPages:
    def test_groups_by_section(self):
        pages = [
            _page("https://ex.com/docs/intro"),
            _page("https://ex.com/docs/advanced"),
            _page("https://ex.com/blog/post1"),
            _page("https://ex.com/about"),
        ]
        sections = group_pages(pages)
        names = [s.name for s in sections]
        assert "Documentation" in names
        assert "About" in names

    def test_section_ordering(self):
        pages = [
            _page("https://ex.com/about"),
            _page("https://ex.com/docs/intro"),
            _page("https://ex.com/blog/post"),
            _page("https://ex.com/api/v1"),
        ]
        sections = group_pages(pages)
        names = [s.name for s in sections]
        assert names.index("Documentation") < names.index("API Reference")
        assert names.index("API Reference") < names.index("About")

    def test_blog_is_optional(self):
        pages = [_page("https://ex.com/blog/post")]
        sections = group_pages(pages)
        blog = next(s for s in sections if s.name == "Blog")
        assert blog.is_optional is True

    def test_within_section_sort_by_depth(self):
        pages = [
            _page("https://ex.com/docs/deep/page", depth=3),
            _page("https://ex.com/docs/intro", depth=1),
        ]
        sections = group_pages(pages)
        doc_section = next(s for s in sections if s.name == "Documentation")
        assert doc_section.pages[0].url == "https://ex.com/docs/intro"

    def test_empty_pages(self):
        assert group_pages([]) == []

    def test_homepage_excluded(self):
        pages = [
            _page("https://ex.com/", title="Home"),
            _page("https://ex.com", title="Home"),
            _page("https://ex.com/docs/intro", title="Intro"),
        ]
        sections = group_pages(pages)
        all_urls = [p.url for s in sections for p in s.pages]
        assert "https://ex.com/" not in all_urls
        assert "https://ex.com" not in all_urls
        assert "https://ex.com/docs/intro" in all_urls

    def test_section_name_refined_from_title(self):
        pages = [
            _page("https://ex.com/cnn-underscored/deals", title="Deals | CNN Underscored"),
            _page("https://ex.com/cnn-underscored/reviews", title="Reviews | CNN Underscored"),
        ]
        sections = group_pages(pages)
        sec = next(s for s in sections if "Underscored" in s.name)
        assert sec.name == "CNN Underscored"

    def test_section_name_keeps_url_fallback_when_no_title_match(self):
        pages = [
            _page("https://ex.com/products/a", title="Widget A"),
            _page("https://ex.com/products/b", title="Widget B"),
        ]
        sections = group_pages(pages)
        sec = next(s for s in sections if "roduct" in s.name)
        assert sec.name == "Products"

    def test_small_unknown_section_is_optional(self):
        pages = [_page("https://ex.com/games/puzzle", title="Puzzle | Games")]
        sections = group_pages(pages)
        games = next(s for s in sections if "Games" in s.name)
        assert games.is_optional is True

    def test_large_unknown_section_is_not_optional(self):
        pages = [
            _page("https://ex.com/products/a", title="A"),
            _page("https://ex.com/products/b", title="B"),
        ]
        sections = group_pages(pages)
        products = next(s for s in sections if "Products" in s.name)
        assert products.is_optional is False

    def test_other_section_is_always_optional(self):
        pages = [
            _page("https://ex.com/x", title="X Page"),
            _page("https://ex.com/y", title="Y Page"),
        ]
        sections = group_pages(pages)
        for s in sections:
            if s.name == "Other":
                assert s.is_optional is True

    def test_known_sections_never_made_optional(self):
        pages = [_page("https://ex.com/about", title="About Us")]
        sections = group_pages(pages)
        about = next(s for s in sections if s.name == "About")
        assert about.is_optional is False

    def test_limits_pages_per_section(self):
        pages = [
            _page(f"https://ex.com/audio/show-{i}", title=f"Show {i}", depth=1)
            for i in range(12)
        ]
        sections = group_pages(pages)
        audio = next(s for s in sections if s.name == "Audio")
        assert len(audio.pages) == 8

    def test_prefers_hub_pages_over_article_like_urls(self):
        pages = [
            _page("https://ex.com/travel", title="Travel", depth=1),
            _page("https://ex.com/travel/destinations", title="Destinations", depth=2),
            _page(
                "https://ex.com/travel/childhood-crush-reunited-romance-chance-encounters",
                title="Article",
                depth=2,
            ),
        ]
        sections = group_pages(pages)
        travel = next(s for s in sections if s.name == "Travel")
        assert [page.url for page in travel.pages[:2]] == [
            "https://ex.com/travel",
            "https://ex.com/travel/destinations",
        ]

    def test_prefers_queryless_urls_after_canonicalization(self):
        pages = [
            _page("https://ex.com/subscription?source=footer", title="Subscribe", depth=1),
            _page("https://ex.com/subscription", title="Subscribe", depth=1),
        ]
        sections = group_pages(pages)
        subscription = next(s for s in sections if s.name == "Subscription")
        assert subscription.pages[0].url == "https://ex.com/subscription"

    def test_deduplicates_pages_by_path(self):
        pages = [
            _page("https://ex.com/docs/intro?ref_=nav", title="Intro", depth=1),
            _page("https://ex.com/docs/intro?ref_=footer", title="Intro", depth=1),
            _page("https://ex.com/docs/intro", title="Intro", depth=1),
        ]
        sections = group_pages(pages)
        doc_section = next(s for s in sections if s.name == "Documentation")
        assert len(doc_section.pages) == 1
        assert doc_section.pages[0].url == "https://ex.com/docs/intro"

    def test_short_segment_pages_go_to_other(self):
        pages = [
            _page("https://ex.com/dp/B07984JN3L", title="Product A"),
            _page("https://ex.com/gp/help/display", title="Help Page"),
        ]
        sections = group_pages(pages)
        other = next((s for s in sections if s.name == "Other"), None)
        assert other is not None
        assert len(other.pages) == 2
        assert other.is_optional is True

    def test_trailing_slash_dedup(self):
        pages = [
            _page("https://ex.com/docs/intro/", title="Intro", depth=1),
            _page("https://ex.com/docs/intro", title="Intro", depth=1),
        ]
        sections = group_pages(pages)
        doc = next(s for s in sections if s.name == "Documentation")
        assert len(doc.pages) == 1

    def test_title_dedup_within_section(self):
        pages = [
            _page("https://ex.com/docs/intro?node=123", title="Introduction", depth=1),
            _page("https://ex.com/docs/getting-started", title="Introduction", depth=1),
        ]
        sections = group_pages(pages)
        doc = next(s for s in sections if s.name == "Documentation")
        assert len(doc.pages) == 1

    def test_canonicalizes_output_urls(self):
        pages = [
            _page("https://ex.com/docs/intro?ref_=nav&utm_source=home", title="Intro"),
        ]
        sections = group_pages(pages)
        doc = next(s for s in sections if s.name == "Documentation")
        assert doc.pages[0].url == "https://ex.com/docs/intro"

    def test_account_section_demoted_to_optional(self):
        pages = [
            _page("https://ex.com/account/settings", title="Settings"),
            _page("https://ex.com/account/payment", title="Payment"),
            _page("https://ex.com/account/login", title="Log In"),
        ]
        sections = group_pages(pages)
        acct = next(s for s in sections if "Account" in s.name)
        assert acct.is_optional is True

    def test_terms_section_demoted_to_optional(self):
        pages = [
            _page("https://ex.com/terms", title="Terms of Service"),
            _page("https://ex.com/terms/privacy", title="Privacy Policy"),
        ]
        sections = group_pages(pages)
        terms = next(s for s in sections if "Terms" in s.name)
        assert terms.is_optional is True

    def test_profiles_section_capped_and_optional(self):
        pages = [
            _page(f"https://ex.com/profiles/person-{i}", title=f"Person {i}")
            for i in range(8)
        ]
        sections = group_pages(pages)
        profiles = next(s for s in sections if "Profiles" in s.name)
        assert profiles.is_optional is True
        assert len(profiles.pages) <= 3

    def test_privacy_section_demoted(self):
        pages = [
            _page("https://ex.com/privacy", title="Privacy Policy"),
        ]
        sections = group_pages(pages)
        privacy = next(s for s in sections if "Privac" in s.name)
        assert privacy.is_optional is True
