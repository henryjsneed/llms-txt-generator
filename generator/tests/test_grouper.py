from llms_txt_generator.persistence.models import PageMetadata
from llms_txt_generator.ranking.grouper import (
    _find_contiguous_match,
    classify_page,
    group_pages,
)


def _page(url: str, title: str = "", depth: int = 0) -> PageMetadata:
    return PageMetadata(url=url, title=title, depth=depth)


class TestClassifyPage:
    def test_first_segment_becomes_section(self):
        """Every path uses first segment directly — no synonym merging."""
        assert classify_page(_page("https://ex.com/docs/intro")) == "Docs"
        assert classify_page(_page("https://ex.com/documentation/api")) == "Documentation"
        assert classify_page(_page("https://ex.com/blog/my-post")) == "Blog"
        assert classify_page(_page("https://ex.com/blogs/archive")) == "Blogs"
        assert classify_page(_page("https://ex.com/guides/setup")) == "Guides"
        assert classify_page(_page("https://ex.com/tutorials/basics")) == "Tutorials"
        assert classify_page(_page("https://ex.com/examples/hello")) == "Examples"
        assert classify_page(_page("https://ex.com/samples/quickstart")) == "Samples"
        assert classify_page(_page("https://ex.com/about")) == "About"
        assert classify_page(_page("https://ex.com/team")) == "Team"
        assert classify_page(_page("https://ex.com/api/v1")) == "Api"
        assert classify_page(_page("https://ex.com/reference/endpoints")) == "Reference"
        assert classify_page(_page("https://ex.com/pricing/plans")) == "Pricing"
        assert classify_page(_page("https://ex.com/faq")) == "Faq"
        assert classify_page(_page("https://ex.com/news/update")) == "News"

    def test_url_structure_only(self):
        """Title content is irrelevant to classification."""
        page = _page(
            "https://docs.stripe.com/billing/billing-apis",
            title="About the Billing APIs",
        )
        assert classify_page(page) == "Billing"

    def test_politics_section(self):
        page = _page(
            "https://ex.com/politics/story",
            title="Deal to reopen DHS sputters on Capitol Hill",
        )
        assert classify_page(page) == "Politics"

    def test_marketplace_section(self):
        page = _page(
            "https://ex.com/marketplace/commands/docs",
            title="docs | Cursor Command",
        )
        assert classify_page(page) == "Marketplace"

    def test_products_section(self):
        page = _page("https://ex.com/products/widget")
        assert classify_page(page) == "Products"

    def test_short_path_segment_falls_to_other(self):
        assert classify_page(_page("https://ex.com/dp/B07984JN3L")) == "Other"
        assert classify_page(_page("https://ex.com/gp/browse")) == "Other"
        assert classify_page(_page("https://ex.com/ap/signin")) == "Other"
        assert classify_page(_page("https://ex.com/b/node123")) == "Other"

    def test_root_returns_other(self):
        assert classify_page(_page("https://ex.com/")) == "Other"

    def test_opaque_url_goes_to_other(self):
        """Title is never used for classification — opaque URLs go to Other."""
        page = _page("https://ex.com/x", title="Getting Started Guide")
        assert classify_page(page) == "Other"

    def test_hyphenated_segment(self):
        assert classify_page(_page("https://ex.com/getting-started/intro")) == "Getting Started"


class TestGroupPages:
    def test_groups_by_section(self):
        pages = [
            _page("https://ex.com/docs/intro"),
            _page("https://ex.com/docs/advanced"),
            _page("https://ex.com/blog/post1"),
            _page("https://ex.com/about"),
            _page("https://ex.com/about/team"),
        ]
        sections = group_pages(pages)
        names = [s.name for s in sections]
        assert "Docs" in names
        assert "About" in names

    def test_section_ordering_by_page_count_then_name(self):
        """Sections ordered by descending page count, then alphabetical."""
        pages = [
            _page("https://ex.com/about/us"),
            _page("https://ex.com/about/team"),
            _page("https://ex.com/about/careers"),
            _page("https://ex.com/docs/intro"),
            _page("https://ex.com/docs/advanced"),
            _page("https://ex.com/pricing/plans"),
            _page("https://ex.com/pricing/enterprise"),
        ]
        sections = group_pages(pages)
        promoted = [s for s in sections if not s.is_optional]
        assert len(promoted[0].pages) == 3

    def test_blog_promoted_with_enough_pages(self):
        pages = [
            _page("https://ex.com/blog/post1"),
            _page("https://ex.com/blog/post2"),
        ]
        sections = group_pages(pages)
        blog = next(s for s in sections if s.name == "Blog")
        assert blog.is_optional is False

    def test_single_page_section_is_optional(self):
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
        doc_section = next(s for s in sections if s.name == "Docs")
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

    def test_all_single_page_sections_are_optional(self):
        pages = [_page("https://ex.com/games/puzzle", title="Puzzle | Games")]
        sections = group_pages(pages)
        games = next(s for s in sections if "Games" in s.name)
        assert games.is_optional is True

    def test_multi_page_section_is_promoted(self):
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
        doc_section = next(s for s in sections if s.name == "Docs")
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
        doc = next(s for s in sections if s.name == "Docs")
        assert len(doc.pages) == 1

    def test_title_dedup_within_section(self):
        pages = [
            _page("https://ex.com/docs/intro?node=123", title="Introduction", depth=1),
            _page("https://ex.com/docs/getting-started", title="Introduction", depth=1),
        ]
        sections = group_pages(pages)
        doc = next(s for s in sections if s.name == "Docs")
        assert len(doc.pages) == 1

    def test_canonicalizes_output_urls(self):
        pages = [
            _page("https://ex.com/docs/intro?ref_=nav&utm_source=home", title="Intro"),
        ]
        sections = group_pages(pages)
        doc = next(s for s in sections if s.name == "Docs")
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

    def test_three_char_section_is_promoted(self):
        """3-char URL segments like 'mac' or 'sdk' are meaningful section names."""
        pages = [
            _page("https://ex.com/mac", title="Mac", depth=1),
            _page("https://ex.com/mac/compare", title="Compare", depth=2),
        ]
        sections = group_pages(pages)
        mac = next(s for s in sections if "Mac" in s.name)
        assert mac.is_optional is False

    def test_section_name_refined_via_contiguous_match(self):
        """'firetv' found as 'Fire TV' in title 'Amazon Fire TV Home'."""
        pages = [
            _page("https://ex.com/firetv", title="Amazon Fire TV Home", depth=0),
            _page("https://ex.com/firetv/devices", title="Streaming Devices", depth=1),
        ]
        sections = group_pages(pages)
        sec = next(s for s in sections if any("firetv" in p.url for p in s.pages))
        assert sec.name == "Fire TV"

    def test_section_name_refined_from_title_segment(self):
        """Section name is refined from page titles when possible."""
        pages = [
            _page("https://ex.com/docs/intro", title="Getting Started | MyApp Docs"),
            _page("https://ex.com/docs/api", title="API | MyApp Docs"),
        ]
        sections = group_pages(pages)
        docs = next(s for s in sections if "ocs" in s.name)
        assert docs.name == "Docs"


class TestDynamicSectionOrdering:
    """Sections are ordered by page count (desc), then alphabetically."""

    def test_larger_sections_come_first(self):
        pages = [
            _page("https://ex.com/alpha/a", title="A1"),
            _page("https://ex.com/zeta/a", title="Z1"),
            _page("https://ex.com/zeta/b", title="Z2"),
            _page("https://ex.com/zeta/c", title="Z3"),
        ]
        sections = group_pages(pages)
        promoted = [s for s in sections if not s.is_optional and s.pages]
        assert promoted[0].name == "Zeta"

    def test_equal_size_sections_ordered_alphabetically(self):
        pages = [
            _page("https://ex.com/docs/intro", title="Intro"),
            _page("https://ex.com/docs/setup", title="Setup"),
            _page("https://ex.com/zeta/a", title="Z1"),
            _page("https://ex.com/zeta/b", title="Z2"),
            _page("https://ex.com/zeta/c", title="Z3"),
        ]
        sections = group_pages(pages)
        promoted = [s for s in sections if not s.is_optional and s.pages]
        assert promoted[0].name == "Zeta"
        assert promoted[1].name == "Docs"


class TestDescriptionPreference:
    """Pages with descriptions should sort ahead of pages without."""

    def test_pages_with_descriptions_rank_first(self):
        pages = [
            _page("https://ex.com/widgets/a", title="Widget A"),
            _page("https://ex.com/widgets/b", title="Widget B"),
            _page("https://ex.com/widgets/c", title="Widget C"),
        ]
        pages[0].description = ""
        pages[1].description = "Has a description"
        pages[2].description = ""
        sections = group_pages(pages)
        widgets = next(s for s in sections if "Widget" in s.name or "widget" in s.name.lower())
        assert widgets.pages[0].description == "Has a description"


class TestChildSectionMerging:
    """Sections whose URL prefix is a dash-prefix of another should merge."""

    def test_merges_when_parent_exists(self):
        """iphone-17-pro merges into iphone because /iphone section exists."""
        pages = [
            _page("https://ex.com/iphone", title="iPhone", depth=1),
            _page("https://ex.com/iphone-17-pro/specs", title="iPhone 17 Pro Specs", depth=2),
            _page("https://ex.com/iphone-air", title="iPhone Air", depth=1),
            _page("https://ex.com/iphone-17", title="iPhone 17", depth=1),
        ]
        sections = group_pages(pages)
        iphone_sections = [s for s in sections if "iphone" in s.name.lower()]
        assert len(iphone_sections) == 1
        assert len(iphone_sections[0].pages) == 4

    def test_no_merge_without_parent(self):
        """macbook-air and macbook-pro stay separate when no /macbook hub exists."""
        pages = [
            _page("https://ex.com/macbook-air", title="MacBook Air", depth=1),
            _page("https://ex.com/macbook-air/specs", title="Specs", depth=2),
            _page("https://ex.com/macbook-pro", title="MacBook Pro", depth=1),
            _page("https://ex.com/macbook-pro/specs", title="Specs", depth=2),
        ]
        sections = group_pages(pages)
        mb_sections = [s for s in sections if "macbook" in s.name.lower()]
        assert len(mb_sections) == 2

    def test_siblings_stay_separate_without_shared_parent(self):
        """apple-card and apple-pay don't merge — neither is a prefix of the other."""
        pages = [
            _page("https://ex.com/apple-card", title="Apple Card", depth=1),
            _page("https://ex.com/apple-card/features", title="Features", depth=2),
            _page("https://ex.com/apple-pay", title="Apple Pay", depth=1),
            _page("https://ex.com/apple-pay/setup", title="Setup", depth=2),
        ]
        sections = group_pages(pages)
        names = [s.name for s in sections if not s.is_optional]
        assert "Apple Card" in names
        assert "Apple Pay" in names

    def test_multi_level_merge(self):
        """mac-mini and mac-pro both merge into mac."""
        pages = [
            _page("https://ex.com/mac", title="Mac", depth=1),
            _page("https://ex.com/mac-mini", title="Mac mini", depth=1),
            _page("https://ex.com/mac-pro", title="Mac Pro", depth=1),
            _page("https://ex.com/mac-studio", title="Mac Studio", depth=1),
        ]
        sections = group_pages(pages)
        mac_sections = [s for s in sections if s.name.lower() == "mac"]
        assert len(mac_sections) == 1
        assert len(mac_sections[0].pages) == 4

    def test_preserves_brand_casing_after_merge(self):
        """Section name should be refined from the shallowest page's title."""
        pages = [
            _page("https://ex.com/iphone", title="iPhone", depth=1),
            _page("https://ex.com/iphone/compare", title="Compare", depth=2),
            _page("https://ex.com/iphone-17", title="iPhone 17", depth=1),
        ]
        sections = group_pages(pages)
        iphone = next(s for s in sections if "phone" in s.name.lower())
        assert iphone.name == "iPhone"

    def test_generic_site_sections_merge(self):
        """Works for any site, not just product catalogs."""
        pages = [
            _page("https://ex.com/services", title="Services", depth=1),
            _page("https://ex.com/services-consulting", title="Consulting", depth=1),
            _page("https://ex.com/services-training", title="Training", depth=1),
        ]
        sections = group_pages(pages)
        svc = [s for s in sections if "services" in s.name.lower()]
        assert len(svc) == 1
        assert len(svc[0].pages) == 3

    def test_dash_child_absorbed_into_parent(self):
        """docs-api merges into docs because /docs-api is a dash-child of /docs."""
        pages = [
            _page("https://ex.com/docs/intro", title="Intro"),
            _page("https://ex.com/docs-api/ref", title="API Ref"),
        ]
        sections = group_pages(pages)
        docs = next(s for s in sections if s.name == "Docs")
        assert len(docs.pages) == 2
        assert len(sections) == 1


class TestContiguousMatch:
    def test_firetv_in_title(self):
        assert _find_contiguous_match("Amazon Fire TV Home", "firetv") == "Fire TV"

    def test_exact_single_word(self):
        assert _find_contiguous_match("Alexa App", "alexa") == "Alexa"

    def test_no_match(self):
        assert _find_contiguous_match("Something Else", "firetv") is None

    def test_multi_word_match(self):
        assert _find_contiguous_match("Amazon Book Review Picks", "amazonbookreview") == "Amazon Book Review"

    def test_preserves_original_casing(self):
        assert _find_contiguous_match("Shop AlexaPlus Now", "alexaplus") == "AlexaPlus"
