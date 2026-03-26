from datetime import datetime, timezone

import boto3

from llms_txt_worker.config import settings
from llms_txt_worker.persistence.models import JobStatus

_kwargs: dict[str, str] = {"region_name": settings.aws_region}
if settings.dynamodb_endpoint:
    _kwargs["endpoint_url"] = settings.dynamodb_endpoint

_dynamodb = boto3.resource("dynamodb", **_kwargs)
_table = _dynamodb.Table(settings.table_name)


def update_job_status(job_id: str, status: JobStatus) -> None:
    _table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": "META"},
        UpdateExpression="SET #s = :status, updated_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": status.value,
            ":now": datetime.now(timezone.utc).isoformat(),
        },
    )


def complete_job(
    job_id: str,
    generated_llms_txt: str,
    site_title: str,
    site_summary: str,
    pages_analyzed: int,
) -> None:
    _table.update_item(
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


def fail_job(job_id: str, error_message: str) -> None:
    _table.update_item(
        Key={"PK": f"JOB#{job_id}", "SK": "META"},
        UpdateExpression="SET #s = :status, updated_at = :now, error_message = :err",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": JobStatus.FAILED.value,
            ":now": datetime.now(timezone.utc).isoformat(),
            ":err": error_message,
        },
    )


def scan_pending_jobs() -> list[dict[str, str]]:
    """Scan for PENDING jobs. Only used by the local dev runner."""
    response = _table.scan(
        FilterExpression="#s = :pending",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":pending": "PENDING"},
    )
    return response.get("Items", [])
