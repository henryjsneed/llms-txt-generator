from enum import Enum

from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PageMetadata(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    depth: int = 0
    status_code: int = 0
