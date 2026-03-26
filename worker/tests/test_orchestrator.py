from llms_txt_worker.crawler.orchestrator import (
    MAX_PAGES_PER_PREFIX,
    _should_skip_page,
    _should_skip_url,
    _top_level_prefix,
    _url_priority,
)
from llms_txt_worker.persistence.models import PageMetadata


class TestShouldSkipUrl:
    def test_skips_pdf(self):
        assert _should_skip_url("https://ex.com/file.pdf") is True

    def test_skips_image(self):
        assert _should_skip_url("https://ex.com/logo.png") is True
        assert _should_skip_url("https://ex.com/photo.jpg") is True

    def test_skips_css_js(self):
        assert _should_skip_url("https://ex.com/style.css") is True
        assert _should_skip_url("https://ex.com/app.js") is True

    def test_skips_login(self):
        assert _should_skip_url("https://ex.com/login") is True
        assert _should_skip_url("https://ex.com/auth/callback") is True

    def test_skips_admin(self):
        assert _should_skip_url("https://ex.com/admin/dashboard") is True

    def test_skips_query_heavy(self):
        assert _should_skip_url("https://ex.com/search?q=test&page=1&sort=asc") is True

    def test_skips_dated_articles(self):
        assert _should_skip_url("https://ex.com/2026/03/25/world/story") is True

    def test_skips_live_news_paths(self):
        assert _should_skip_url("https://ex.com/world/live-news/story") is True

    def test_skips_generic_video_title_pages(self):
        assert _should_skip_url("https://ex.com/videos/title-2258052") is True

    def test_skips_sitemap_index_pages(self):
        assert _should_skip_url("https://ex.com/gallery/sitemap-2011.html") is True
        assert _should_skip_url("https://ex.com/profile/sitemap-2019.html") is True
        assert _should_skip_url("https://ex.com/article/sitemap2014.html") is True

    def test_allows_normal_html_pages(self):
        assert _should_skip_url("https://ex.com/sitemap.html") is False

    def test_allows_normal_pages(self):
        assert _should_skip_url("https://ex.com/docs/intro") is False
        assert _should_skip_url("https://ex.com/about") is False
        assert _should_skip_url("https://ex.com/blog/my-post") is False

    def test_allows_single_query_param(self):
        assert _should_skip_url("https://ex.com/page?ref=home") is False


class TestUrlPriority:
    def test_prefers_docs_over_marketplace(self):
        assert _url_priority("https://ex.com/docs") < _url_priority("https://ex.com/marketplace")

    def test_prefers_shallow_hub_pages(self):
        assert _url_priority("https://ex.com/world") < _url_priority("https://ex.com/world/europe/ukraine")

    def test_root_is_highest_priority(self):
        assert _url_priority("https://ex.com/") < _url_priority("https://ex.com/docs")

    def test_preferred_prefixes_same_rank(self):
        docs = _url_priority("https://ex.com/docs")
        help_ = _url_priority("https://ex.com/help")
        assert docs[0] == help_[0] == 0

    def test_deprioritized_prefixes_rank(self):
        mp = _url_priority("https://ex.com/marketplace/item")
        blog = _url_priority("https://ex.com/blog/post")
        assert mp[0] == blog[0] == 2

    def test_default_rank_between_preferred_and_deprioritized(self):
        default = _url_priority("https://ex.com/world")
        preferred = _url_priority("https://ex.com/docs")
        deprioritized = _url_priority("https://ex.com/marketplace")
        assert preferred < default < deprioritized

    def test_within_same_rank_prefers_shallower(self):
        shallow = _url_priority("https://ex.com/docs")
        deep = _url_priority("https://ex.com/docs/api/v2/endpoints")
        assert shallow < deep

    def test_returns_tuple_for_heap_ordering(self):
        result = _url_priority("https://ex.com/docs")
        assert isinstance(result, tuple)
        assert len(result) == 3


class TestTopLevelPrefix:
    def test_extracts_first_segment(self):
        assert _top_level_prefix("https://ex.com/marketplace/item-1") == "marketplace"

    def test_root_returns_empty(self):
        assert _top_level_prefix("https://ex.com/") == ""
        assert _top_level_prefix("https://ex.com") == ""

    def test_deep_path(self):
        assert _top_level_prefix("https://ex.com/docs/api/v2") == "docs"


class TestPrefixQuotaConstant:
    def test_max_pages_per_prefix_is_positive(self):
        assert MAX_PAGES_PER_PREFIX > 0

    def test_max_pages_per_prefix_is_reasonable(self):
        assert MAX_PAGES_PER_PREFIX <= 30


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

    def test_keeps_normal_pages(self):
        page = PageMetadata(
            url="https://ex.com/docs",
            title="Docs",
            description="Documentation landing page",
            status_code=200,
        )
        assert _should_skip_page(page) is False
