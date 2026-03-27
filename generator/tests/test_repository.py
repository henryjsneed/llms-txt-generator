from llms_txt_generator.persistence.models import JobStatus
from llms_txt_generator.persistence.repository import (
    complete_job,
    fail_job,
    scan_pending_jobs,
    update_job_status,
)


def _seed_job(table, job_id: str, status: str = "PENDING") -> None:
    table.put_item(
        Item={
            "PK": f"JOB#{job_id}",
            "SK": "META",
            "status": status,
            "input_url": "https://example.com",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )


def _get_job(table, job_id: str) -> dict:
    result = table.get_item(Key={"PK": f"JOB#{job_id}", "SK": "META"})
    return result["Item"]


class TestUpdateJobStatus:
    def test_sets_status_and_updated_at(self, moto_table):
        _seed_job(moto_table, "j1")
        update_job_status("j1", JobStatus.RUNNING)

        item = _get_job(moto_table, "j1")
        assert item["status"] == "RUNNING"
        assert item["updated_at"] != "2026-01-01T00:00:00+00:00"


class TestCompleteJob:
    def test_stores_result_fields(self, moto_table):
        _seed_job(moto_table, "j2")
        complete_job(
            job_id="j2",
            generated_llms_txt="# Site\n",
            site_title="Site",
            site_summary="A site",
            pages_analyzed=10,
        )

        item = _get_job(moto_table, "j2")
        assert item["status"] == "COMPLETED"
        assert item["generated_llms_txt"] == "# Site\n"
        assert item["site_title"] == "Site"
        assert item["site_summary"] == "A site"
        assert item["pages_analyzed"] == 10


class TestFailJob:
    def test_stores_error_message(self, moto_table):
        _seed_job(moto_table, "j3")
        fail_job("j3", "Crawl timed out")

        item = _get_job(moto_table, "j3")
        assert item["status"] == "FAILED"
        assert item["error_message"] == "Crawl timed out"


class TestScanPendingJobs:
    def test_returns_only_pending(self, moto_table):
        _seed_job(moto_table, "p1", status="PENDING")
        _seed_job(moto_table, "p2", status="PENDING")
        _seed_job(moto_table, "r1", status="RUNNING")

        results = scan_pending_jobs()
        job_ids = {item["PK"] for item in results}
        assert job_ids == {"JOB#p1", "JOB#p2"}

    def test_empty_table(self, moto_table):
        assert scan_pending_jobs() == []
