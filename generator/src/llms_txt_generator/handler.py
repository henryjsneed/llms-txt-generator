"""AWS Lambda handler: consumes SQS events and runs the crawl-to-llms.txt pipeline."""

import asyncio
import json
import logging
from typing import Any

from llms_txt_generator.crawler.fetcher import SSRFError, validate_url
from llms_txt_generator.crawler.orchestrator import crawl
from llms_txt_generator.generator.llms_txt import generate_llms_txt
from llms_txt_generator.persistence.models import JobStatus
from llms_txt_generator.persistence.repository import complete_job, fail_job, update_job_status
from llms_txt_generator.ranking.grouper import group_pages

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

MIN_USEFUL_PAGES = 3


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
        logger.warning("Job %s URL validation failed: %s", job_id, exc)
        fail_job(job_id, f"URL validation failed: {exc}")
        return

    try:
        pages, site_title, site_summary, stats = asyncio.run(crawl(url))
    except Exception as exc:
        logger.exception("Crawl failed for job %s", job_id)
        fail_job(job_id, f"Crawl failed: {exc}")
        return

    logger.info(
        "Job %s crawl returned %d page(s) from %d fetches, site_title=%r",
        job_id, len(pages), stats.total_fetches,
        site_title[:80] if site_title else "",
    )

    if not pages:
        if stats.skipped_quality > 0:
            msg = (
                "This website blocks automated access — all crawled pages "
                "returned errors or bot detection challenges. "
                "A useful llms.txt cannot be produced for this URL."
            )
        elif stats.skipped_errors > 0:
            msg = (
                "All requests to this website failed. The site may be "
                "temporarily unavailable or blocking automated access."
            )
        else:
            msg = "No pages could be crawled from this URL."
        logger.warning("Job %s failed: %s", job_id, msg)
        fail_job(job_id, msg)
        return

    if stats.is_aggressively_blocked(len(pages)):
        msg = (
            "This website actively blocks automated access — only "
            f"{len(pages)} of {stats.total_fetches} requests succeeded. "
            "The generated output would not accurately represent the site. "
            "A useful llms.txt cannot be produced for this URL."
        )
        logger.warning("Job %s failed: %s", job_id, msg)
        fail_job(job_id, msg)
        return

    if len(pages) < MIN_USEFUL_PAGES:
        few_fetches = stats.total_fetches <= MIN_USEFUL_PAGES
        no_failures = stats.skipped_errors == 0 and stats.skipped_quality == 0
        if few_fetches and no_failures:
            msg = (
                "Not enough content found on this site to generate a useful llms.txt. "
                "The homepage may have no same-site links, or the site may be too small. "
                "Try a more specific URL within the site."
            )
        else:
            msg = (
                f"Only {len(pages)} page(s) crawled — the site may be blocking automated "
                "requests. Try a different URL or a site with less aggressive bot protection."
            )
        logger.warning("Job %s failed: %s", job_id, msg)
        fail_job(job_id, msg)
        return

    high_skip_rate = (stats.skipped_quality + stats.skipped_errors) > len(pages) * 2
    if high_skip_rate:
        msg = (
            "This website appears to block automated access — most crawled pages "
            f"returned errors or bot challenges ({len(pages)} usable out of "
            f"{stats.total_fetches} fetched). "
            "A useful llms.txt cannot be produced for this URL."
        )
        logger.warning("Job %s failed: %s", job_id, msg)
        fail_job(job_id, msg)
        return

    sections = group_pages(pages)
    llms_txt = generate_llms_txt(
        site_title=site_title or url,
        site_summary=site_summary,
        sections=sections,
    )

    logger.info(
        "Job %s completed: %d pages, %d sections, output=%d chars",
        job_id, len(pages), len(sections), len(llms_txt),
    )
    complete_job(
        job_id=job_id,
        generated_llms_txt=llms_txt,
        site_title=site_title or url,
        site_summary=site_summary,
        pages_analyzed=len(pages),
    )
