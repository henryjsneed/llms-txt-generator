import functools
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from llms_txt_generator.config import settings
from llms_txt_generator.persistence.models import JobStatus

logger = logging.getLogger(__name__)


@functools.cache
def _get_table() -> Any:
    """Lazily create and cache the DynamoDB Table resource."""
    kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint
    dynamodb = boto3.resource("dynamodb", **kwargs)
    return dynamodb.Table(settings.dynamodb_table_name)


def update_job_status(job_id: str, status: JobStatus) -> None:
    try:
        _get_table().update_item(
            Key={"PK": f"JOB#{job_id}", "SK": "META"},
            UpdateExpression="SET #s = :status, updated_at = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": status.value,
                ":now": datetime.now(timezone.utc).isoformat(),
            },
        )
    except ClientError:
        logger.exception("DynamoDB update_job_status failed for job %s", job_id)
        raise


def complete_job(
    job_id: str,
    generated_llms_txt: str,
    site_title: str,
    site_summary: str,
    pages_analyzed: int,
) -> None:
    try:
        _get_table().update_item(
            Key={"PK": f"JOB#{job_id}", "SK": "META"},
            UpdateExpression=(
                "SET #s = :status, updated_at = :now, "
                "generated_llms_txt = :txt, site_title = :title, "
                "site_summary = :summary, pages_analyzed = :count"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": JobStatus.COMPLETED.value,
                ":now": datetime.now(timezone.utc).isoformat(),
                ":txt": generated_llms_txt,
                ":title": site_title,
                ":summary": site_summary,
                ":count": pages_analyzed,
            },
        )
    except ClientError:
        logger.exception("DynamoDB complete_job failed for job %s", job_id)
        raise


def fail_job(job_id: str, error_message: str) -> None:
    try:
        _get_table().update_item(
            Key={"PK": f"JOB#{job_id}", "SK": "META"},
            UpdateExpression="SET #s = :status, updated_at = :now, error_message = :err",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": JobStatus.FAILED.value,
                ":now": datetime.now(timezone.utc).isoformat(),
                ":err": error_message,
            },
        )
    except ClientError:
        logger.exception("DynamoDB fail_job failed for job %s", job_id)
        raise


def scan_pending_jobs() -> list[dict[str, Any]]:
    """Scan for PENDING jobs. Only used by the local dev runner."""
    response = _get_table().scan(
        FilterExpression="#s = :pending",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":pending": "PENDING"},
    )
    return response.get("Items", [])
