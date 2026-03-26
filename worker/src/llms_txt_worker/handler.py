"""AWS Lambda handler: consumes SQS events and runs the crawl-to-llms.txt pipeline."""

import asyncio
import json
import logging
from typing import Any

from llms_txt_worker.crawler.fetcher import SSRFError, validate_url
from llms_txt_worker.crawler.orchestrator import crawl
from llms_txt_worker.generator.llms_txt import generate_llms_txt
from llms_txt_worker.persistence.models import JobStatus
from llms_txt_worker.persistence.repository import complete_job, fail_job, update_job_status
from llms_txt_worker.ranking.grouper import group_pages

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Entry point for Lambda. Processes one SQS message at a time."""
    for record in event.get("Records", []):
        body = json.loads(record["body"])
        job_id = body["job_id"]
        url = body["url"]
        logger.info("Processing job %s for URL %s", job_id, url)

        try:
            _process_job(job_id, url)
        except Exception:
            logger.exception("Unhandled error processing job %s", job_id)
            fail_job(job_id, "Internal processing error")

    return {"statusCode": 200}


def _process_job(job_id: str, url: str) -> None:
    update_job_status(job_id, JobStatus.RUNNING)

    try:
        validate_url(url)
    except SSRFError as exc:
        fail_job(job_id, f"URL validation failed: {exc}")
        return

    try:
        pages, site_title, site_summary = asyncio.run(crawl(url))
    except Exception as exc:
        logger.exception("Crawl failed for job %s", job_id)
        fail_job(job_id, f"Crawl failed: {exc}")
        return

    if not pages:
        fail_job(job_id, "No pages could be crawled from this URL")
        return

    sections = group_pages(pages)
    llms_txt = generate_llms_txt(
        site_title=site_title or url,
        site_summary=site_summary,
        sections=sections,
    )

    complete_job(
        job_id=job_id,
        generated_llms_txt=llms_txt,
        site_title=site_title or url,
        site_summary=site_summary,
        pages_analyzed=len(pages),
    )
    logger.info("Job %s completed: %d pages, %d sections", job_id, len(pages), len(sections))
