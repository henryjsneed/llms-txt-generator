from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Worker configuration populated from environment variables."""

    table_name: str = "llms-txt-generator"
    aws_region: str = "us-east-1"
    dynamodb_endpoint: str | None = None

    max_pages: int = 125
    max_depth: int = 3
    max_concurrency: int = 10
    per_request_timeout: int = 10
    total_crawl_timeout: int = 180
    max_response_size: int = 5 * 1024 * 1024

    model_config = {"env_prefix": ""}


settings = Settings()
