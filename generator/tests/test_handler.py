from unittest.mock import AsyncMock, patch

from llms_txt_generator.crawler.orchestrator import CrawlStats
from llms_txt_generator.handler import _process_job
from llms_txt_generator.persistence.models import PageMetadata


def _seed_pending_job(table, job_id: str, url: str = "https://example.com") -> None:
    table.put_item(
        Item={
            "PK": f"JOB#{job_id}",
            "SK": "META",
            "status": "PENDING",
            "input_url": url,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )


def _get_job(table, job_id: str) -> dict:
    return table.get_item(Key={"PK": f"JOB#{job_id}", "SK": "META"})["Item"]


def _make_pages(count: int) -> list[PageMetadata]:
    return [
        PageMetadata(
            url=f"https://example.com/page-{i}",
            title=f"Page {i}",
            description=f"Description {i}",
            depth=1,
            status_code=200,
        )
        for i in range(count)
    ]


class TestProcessJobSuccess:
    def test_completes_with_generated_output(self, moto_table):
        _seed_pending_job(moto_table, "j1")
        pages = _make_pages(5)
        stats = CrawlStats(total_fetches=6)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=(pages, "Example Site", "A great site", stats),
        ):
            _process_job("j1", "https://example.com")

        item = _get_job(moto_table, "j1")
        assert item["status"] == "COMPLETED"
        assert "# Example Site" in item["generated_llms_txt"]
        assert item["pages_analyzed"] == 5


class TestProcessJobUrlValidation:
    def test_rejects_ssrf_url(self, moto_table):
        _seed_pending_job(moto_table, "j2", url="file:///etc/passwd")

        _process_job("j2", "file:///etc/passwd")

        item = _get_job(moto_table, "j2")
        assert item["status"] == "FAILED"
        assert "URL validation failed" in item["error_message"]


class TestProcessJobCrawlFailure:
    def test_crawl_exception_fails_job(self, moto_table):
        _seed_pending_job(moto_table, "j3")

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            _process_job("j3", "https://example.com")

        item = _get_job(moto_table, "j3")
        assert item["status"] == "FAILED"
        assert "Crawl failed" in item["error_message"]


class TestProcessJobNoPages:
    def test_zero_pages_with_quality_skips(self, moto_table):
        _seed_pending_job(moto_table, "j4")
        stats = CrawlStats(total_fetches=5, skipped_quality=5)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=([], "", "", stats),
        ):
            _process_job("j4", "https://example.com")

        item = _get_job(moto_table, "j4")
        assert item["status"] == "FAILED"
        assert "blocks automated access" in item["error_message"]

    def test_zero_pages_with_errors(self, moto_table):
        _seed_pending_job(moto_table, "j5")
        stats = CrawlStats(total_fetches=5, skipped_errors=5)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=([], "", "", stats),
        ):
            _process_job("j5", "https://example.com")

        item = _get_job(moto_table, "j5")
        assert item["status"] == "FAILED"
        assert "requests to this website failed" in item["error_message"]

    def test_zero_pages_generic(self, moto_table):
        _seed_pending_job(moto_table, "j6")
        stats = CrawlStats(total_fetches=0)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=([], "", "", stats),
        ):
            _process_job("j6", "https://example.com")

        item = _get_job(moto_table, "j6")
        assert item["status"] == "FAILED"
        assert "No pages could be crawled" in item["error_message"]


class TestProcessJobAggressiveBlocking:
    def test_high_failure_rate_detected(self, moto_table):
        _seed_pending_job(moto_table, "j7")
        pages = _make_pages(2)
        stats = CrawlStats(total_fetches=100, skipped_quality=98)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=(pages, "Blocked Site", "", stats),
        ):
            _process_job("j7", "https://example.com")

        item = _get_job(moto_table, "j7")
        assert item["status"] == "FAILED"
        assert "actively blocks" in item["error_message"]


class TestProcessJobTooFewPages:
    def test_fewer_than_minimum_useful(self, moto_table):
        _seed_pending_job(moto_table, "j8")
        pages = _make_pages(2)
        stats = CrawlStats(total_fetches=10)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=(pages, "Small Site", "", stats),
        ):
            _process_job("j8", "https://example.com")

        item = _get_job(moto_table, "j8")
        assert item["status"] == "FAILED"
        assert "2 page(s) crawled" in item["error_message"]

    def test_portal_site_with_no_same_host_links(self, moto_table):
        """Sites like www.wikipedia.org have a homepage but no same-host links."""
        _seed_pending_job(moto_table, "j9")
        pages = _make_pages(1)
        stats = CrawlStats(total_fetches=1)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=(pages, "Wikipedia", "", stats),
        ):
            _process_job("j9", "https://www.wikipedia.org")

        item = _get_job(moto_table, "j9")
        assert item["status"] == "FAILED"
        assert "Not enough content" in item["error_message"]
        assert "blocking" not in item["error_message"]


class TestProcessJobHighSkipRate:
    def test_many_skips_relative_to_kept_pages(self, moto_table):
        """Walmart second-crawl scenario: few pages pass but many were blocked."""
        _seed_pending_job(moto_table, "j10")
        pages = _make_pages(4)
        stats = CrawlStats(total_fetches=20, skipped_quality=15)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=(pages, "Walmart", "", stats),
        ):
            _process_job("j10", "https://www.walmart.com")

        item = _get_job(moto_table, "j10")
        assert item["status"] == "FAILED"
        assert "block" in item["error_message"].lower()

    def test_healthy_crawl_not_flagged(self, moto_table):
        """Normal crawl with some skips should not be flagged."""
        _seed_pending_job(moto_table, "j11")
        pages = _make_pages(50)
        stats = CrawlStats(total_fetches=60, skipped_quality=5)

        with patch(
            "llms_txt_generator.handler.crawl",
            new_callable=AsyncMock,
            return_value=(pages, "Good Site", "A good site", stats),
        ):
            _process_job("j11", "https://example.com")

        item = _get_job(moto_table, "j11")
        assert item["status"] == "COMPLETED"
