from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_sqs as sqs,
)
from constructs import Construct


class BackendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        table = dynamodb.Table(
            self,
            "JobsTable",
            table_name="llms-txt-generator",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY,
        )

        dlq = sqs.Queue(
            self,
            "CrawlDLQ",
            queue_name="llms-txt-crawl-dlq",
            retention_period=Duration.days(7),
        )

        queue = sqs.Queue(
            self,
            "CrawlQueue",
            queue_name="llms-txt-crawl-queue",
            visibility_timeout=Duration.seconds(330),
            retention_period=Duration.hours(1),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq),
        )

        worker_fn = lambda_.DockerImageFunction(
            self,
            "WorkerFunction",
            function_name="llms-txt-worker",
            architecture=lambda_.Architecture.X86_64,
            code=lambda_.DockerImageCode.from_image_asset(
                "../worker",
                platform=ecr_assets.Platform.LINUX_AMD64,
            ),
            memory_size=1024,
            timeout=Duration.minutes(5),
            environment={
                "TABLE_NAME": table.table_name,
            },
        )

        worker_fn.add_event_source(
            event_sources.SqsEventSource(queue, batch_size=1)
        )

        table.grant_read_write_data(worker_fn)

        amplify_policy = iam.ManagedPolicy(
            self,
            "AmplifyPolicy",
            managed_policy_name="llms-txt-amplify-policy",
            statements=[
                iam.PolicyStatement(
                    actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:DeleteItem"],
                    resources=[table.table_arn],
                ),
                iam.PolicyStatement(
                    actions=["sqs:SendMessage"],
                    resources=[queue.queue_arn],
                ),
            ],
        )

        CfnOutput(self, "TableName", value=table.table_name)
        CfnOutput(self, "QueueUrl", value=queue.queue_url)
        CfnOutput(self, "AmplifyPolicyArn", value=amplify_policy.managed_policy_arn)
        CfnOutput(self, "DlqUrl", value=dlq.queue_url)
