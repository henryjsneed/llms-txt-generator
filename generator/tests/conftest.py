from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")


@pytest.fixture
def moto_table():
    """Provide a moto-backed DynamoDB table and patch repository._get_table."""
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-west-2")
        table = resource.create_table(
            TableName="llms-txt-generator",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName="llms-txt-generator")

        with patch("llms_txt_generator.persistence.repository._get_table", return_value=table):
            yield table
