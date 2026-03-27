"""Local development runner. Polls DynamoDB Local for PENDING jobs and processes them.

Usage:
    DYNAMODB_ENDPOINT=http://localhost:8000 python -m llms_txt_generator.dev_runner

Replaces SQS + Lambda for local development. The Next.js dev server creates PENDING
jobs in DynamoDB Local and this script picks them up and runs the full pipeline.
"""

import logging
import os
import sys
import time

from llms_txt_generator.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not settings.dynamodb_endpoint:
        logger.error(
            "DYNAMODB_ENDPOINT is not set. Example: "
            "DYNAMODB_ENDPOINT=http://localhost:8000 python -m llms_txt_generator.dev_runner "
            "(use one line, or export the variable first)."
        )
        sys.exit(1)

    # Provide placeholder credentials so boto3 skips the real credential chain
    # DynamoDB Local accepts any key pair
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")

    from llms_txt_generator.handler import _process_job
    from llms_txt_generator.persistence.repository import scan_pending_jobs

    logger.info("Local dev runner started — polling for PENDING jobs...")
    while True:
        try:
            jobs = scan_pending_jobs()
            for item in jobs:
                job_id = item["PK"].removeprefix("JOB#")
                url = item.get("normalized_url") or item.get("input_url", "")
                if not url:
                    continue
                logger.info("Processing job %s for %s", job_id, url)
                try:
                    _process_job(job_id, url)
                except Exception:
                    logger.exception("Failed to process job %s", job_id)
        except Exception:
            logger.exception("Error scanning for jobs")

        time.sleep(2)


if __name__ == "__main__":
    main()
