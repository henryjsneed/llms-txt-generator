from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Generator configuration populated from environment variables."""

    dynamodb_table_name: str = "llms-txt-generator"
    aws_region: str = "us-west-2"
    dynamodb_endpoint: str | None = None

    max_pages: int = 300
    max_depth: int = 3
    max_concurrency: int = 5
    per_request_timeout: int = 10
    total_crawl_timeout: int = 180
    max_response_size: int = 5 * 1024 * 1024

    model_config = {"env_prefix": ""}


settings = Settings()
