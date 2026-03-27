from llms_txt_generator.config import settings
from llms_txt_generator.crawler.orchestrator import (
    BLOCK_DETECTION_MAX_SUCCESS_RATE,
    BLOCK_DETECTION_MIN_FETCHES,
    MAX_TOTAL_FETCHES_MULTIPLIER,
    CrawlStats,
    _should_skip_page,
    _should_skip_url,
    _top_level_prefix,
    _url_priority,
)
from llms_txt_generator.persistence.models import PageMetadata


class TestShouldSkipUrl:
    def test_skips_pdf(self):
        assert _should_skip_url("https://ex.com/file.pdf") is True

    def test_skips_image(self):
        assert _should_skip_url("https://ex.com/logo.png") is True
        assert _should_skip_url("https://ex.com/photo.jpg") is True

    def test_skips_css_js(self):
        assert _should_skip_url("https://ex.com/style.css") is True
        assert _should_skip_url("https://ex.com/app.js") is True

    def test_skips_office_docs(self):
        assert _should_skip_url("https://ex.com/report.docx") is True
        assert _should_skip_url("https://ex.com/data.xlsx") is True
        assert _should_skip_url("https://ex.com/deck.pptx") is True

    def test_skips_archives(self):
        assert _should_skip_url("https://ex.com/file.7z") is True
        assert _should_skip_url("https://ex.com/file.rar") is True

    def test_skips_video(self):
        assert _should_skip_url("https://ex.com/clip.webm") is True
        assert _should_skip_url("https://ex.com/movie.mov") is True

    def test_skips_login(self):
        assert _should_skip_url("https://ex.com/login") is True
        assert _should_skip_url("https://ex.com/auth/callback") is True

    def test_skips_admin(self):
        assert _should_skip_url("https://ex.com/admin/dashboard") is True

    def test_skips_cart_checkout(self):
        assert _should_skip_url("https://ex.com/cart") is True
        assert _should_skip_url("https://ex.com/checkout") is True

    def test_skips_search(self):
        assert _should_skip_url("https://ex.com/search?q=test") is True

    def test_skips_error_pages(self):
        assert _should_skip_url("https://ex.com/404") is True
        assert _should_skip_url("https://ex.com/500") is True
        assert _should_skip_url("https://ex.com/blocked") is True

    def test_skips_query_heavy(self):
        assert _should_skip_url("https://ex.com/search?q=test&page=1&sort=asc") is True

    def test_skips_dated_articles(self):
        assert _should_skip_url("https://ex.com/2026/03/25/world/story") is True

    def test_skips_sitemap_index_pages(self):
        assert _should_skip_url("https://ex.com/gallery/sitemap-2011.html") is True
        assert _should_skip_url("https://ex.com/profile/sitemap-2019.html") is True
        assert _should_skip_url("https://ex.com/article/sitemap2014.html") is True

    def test_allows_normal_html_pages(self):
        assert _should_skip_url("https://ex.com/sitemap.html") is False

    def test_skips_locale_prefix_lang_region(self):
        assert _should_skip_url("https://ex.com/en-ca/about") is True
        assert _should_skip_url("https://ex.com/en-gb/privacy") is True
        assert _should_skip_url("https://ex.com/es-us/menu") is True
        assert _should_skip_url("https://ex.com/fr-ca/accueil") is True

    def test_skips_bare_locale_path(self):
        assert _should_skip_url("https://ex.com/en-ca") is True
        assert _should_skip_url("https://ex.com/de-de") is True

    def test_skips_two_letter_country_code_paths(self):
        assert _should_skip_url("https://ex.com/ae") is True
        assert _should_skip_url("https://ex.com/br") is True
        assert _should_skip_url("https://ex.com/au/page") is True

    def test_skips_locale_with_three_letter_suffix(self):
        assert _should_skip_url("https://ex.com/us-edu/store") is True
        assert _should_skip_url("https://ex.com/us_epp/store") is True

    def test_allows_non_locale_similar_paths(self):
        assert _should_skip_url("https://ex.com/about-us") is False
        assert _should_skip_url("https://ex.com/brand-assets/photos") is False
        assert _should_skip_url("https://ex.com/mac") is False
        assert _should_skip_url("https://ex.com/docs/intro") is False

    def test_skips_uuid_path_segments(self):
        assert _should_skip_url(
            "https://ex.com/careers/03e0b0f5-9d1e-4f11-8a63-dfc50e09f887"
        ) is True
        assert _should_skip_url(
            "https://ex.com/jobs/261793a4-1711-4c02-b58b-96b0f984b672/apply"
        ) is True

    def test_allows_non_uuid_hex_paths(self):
        assert _should_skip_url("https://ex.com/docs/abcdef12") is False

    def test_allows_normal_pages(self):
        assert _should_skip_url("https://ex.com/docs/intro") is False
        assert _should_skip_url("https://ex.com/about") is False
        assert _should_skip_url("https://ex.com/blog/my-post") is False

    def test_allows_single_query_param(self):
        assert _should_skip_url("https://ex.com/page?ref=home") is False

    def test_allows_product_and_commerce_pages(self):
        """No opinionated e-commerce filtering — let the site structure decide."""
        assert _should_skip_url("https://ex.com/product/widget-123") is False
        assert _should_skip_url("https://ex.com/brand/acme") is False
        assert _should_skip_url("https://ex.com/reviews/product-abc") is False
        assert _should_skip_url("https://ex.com/releases/v2.0.0") is False


class TestUrlPriority:
    def test_prefers_shallow_over_deep(self):
        assert _url_priority("https://ex.com/docs") < _url_priority("https://ex.com/docs/api/v2")

    def test_root_is_highest_priority(self):
        assert _url_priority("https://ex.com/") < _url_priority("https://ex.com/docs")

    def test_same_depth_equal_priority(self):
        """No alphabetical or content-type bias — same depth = same priority."""
        assert _url_priority("https://ex.com/docs") == _url_priority("https://ex.com/marketplace")
        assert _url_priority("https://ex.com/blog") == _url_priority("https://ex.com/about")


class TestTopLevelPrefix:
    def test_extracts_first_segment(self):
        assert _top_level_prefix("https://ex.com/marketplace/item-1") == "marketplace"

    def test_root_returns_empty(self):
        assert _top_level_prefix("https://ex.com/") == ""
        assert _top_level_prefix("https://ex.com") == ""

    def test_deep_path(self):
        assert _top_level_prefix("https://ex.com/docs/api/v2") == "docs"


class TestShouldSkipPage:
    def test_skips_captcha_pages(self):
        page = PageMetadata(
            url="https://ex.com/protected",
            title="Access to this page has been denied",
            description="px-captcha",
            status_code=200,
        )
        assert _should_skip_page(page) is True

    def test_skips_http_error_pages(self):
        page = PageMetadata(
            url="https://ex.com/missing",
            title="Not Found",
            description="",
            status_code=404,
        )
        assert _should_skip_page(page) is True

    def test_skips_bot_detection_pages(self):
        page = PageMetadata(
            url="https://ex.com/blocked",
            title="Robot or human?",
            description="",
            status_code=200,
        )
        assert _should_skip_page(page) is True

    def test_skips_browser_check_page(self):
        page = PageMetadata(
            url="https://ex.com/",
            title="Just a moment...",
            description="Checking your browser",
            status_code=200,
        )
        assert _should_skip_page(page) is True

    def test_skips_soft_404_pages(self):
        page = PageMetadata(
            url="https://ex.com/election/2018/NoLinkState",
            title="Uh Oh!",
            description="There is no page here.",
            status_code=200,
        )
        assert _should_skip_page(page) is True

    def test_skips_something_went_wrong(self):
        page = PageMetadata(
            url="https://ex.com/broken",
            title="Something went wrong.",
            description="",
            status_code=200,
        )
        assert _should_skip_page(page) is True

    def test_skips_template_variable_titles(self):
        page = PageMetadata(
            url="https://ex.com/markets/stocks/JD",
            title="__symbol__ Stock Quote Price and Forecast",
            description="",
            status_code=200,
        )
        assert _should_skip_page(page) is True

    def test_keeps_normal_pages(self):
        page = PageMetadata(
            url="https://ex.com/docs",
            title="Docs",
            description="Documentation landing page",
            status_code=200,
        )
        assert _should_skip_page(page) is False


class TestCrawlStatsBudget:
    def test_budget_not_exhausted_initially(self):
        stats = CrawlStats()
        assert stats.budget_exhausted is False

    def test_budget_exhausted_at_threshold(self):
        stats = CrawlStats()
        stats.total_fetches = settings.max_pages * MAX_TOTAL_FETCHES_MULTIPLIER
        assert stats.budget_exhausted is True

    def test_budget_not_exhausted_below_threshold(self):
        stats = CrawlStats()
        stats.total_fetches = settings.max_pages * MAX_TOTAL_FETCHES_MULTIPLIER - 1
        assert stats.budget_exhausted is False


class TestAggressiveBlockDetection:
    def test_high_failure_rate_detected(self):
        stats = CrawlStats(total_fetches=2252, skipped_quality=2230)
        assert stats.is_aggressively_blocked(pages_kept=22) is True

    def test_cooperative_site_not_flagged(self):
        stats = CrawlStats(total_fetches=160)
        assert stats.is_aggressively_blocked(pages_kept=150) is False

    def test_small_sample_not_flagged(self):
        stats = CrawlStats(total_fetches=10)
        assert stats.is_aggressively_blocked(pages_kept=1) is False

    def test_borderline_rate_not_flagged(self):
        fetches = BLOCK_DETECTION_MIN_FETCHES
        pages = int(fetches * BLOCK_DETECTION_MAX_SUCCESS_RATE) + 1
        stats = CrawlStats(total_fetches=fetches)
        assert stats.is_aggressively_blocked(pages_kept=pages) is False

    def test_borderline_rate_flagged(self):
        fetches = 100
        pages = int(fetches * BLOCK_DETECTION_MAX_SUCCESS_RATE) - 1
        stats = CrawlStats(total_fetches=fetches)
        assert stats.is_aggressively_blocked(pages_kept=pages) is True
