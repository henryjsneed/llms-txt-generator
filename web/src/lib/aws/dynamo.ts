import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand, GetCommand, DeleteCommand } from "@aws-sdk/lib-dynamodb";
import type { Job, JobStatus } from "../types";
import { env } from "../env";

const client = new DynamoDBClient({
  region: env.region,
  ...(env.dynamoEndpoint && { endpoint: env.dynamoEndpoint }),
});

const docClient = DynamoDBDocumentClient.from(client);

const TABLE_NAME = env.tableName;

export async function createJob(
  jobId: string,
  inputUrl: string,
  normalizedUrl: string,
): Promise<{ created_at: string }> {
  const now = new Date().toISOString();
  const expiresAt = Math.floor(Date.now() / 1000) + 86400;

  await docClient.send(
    new PutCommand({
      TableName: TABLE_NAME,
      Item: {
        PK: `JOB#${jobId}`,
        SK: "META",
        input_url: inputUrl,
        normalized_url: normalizedUrl,
        status: "PENDING" as JobStatus,
        created_at: now,
        updated_at: now,
        expires_at: expiresAt,
      },
    })
  );

  return { created_at: now };
}

export async function deleteJob(jobId: string): Promise<void> {
  await docClient.send(
    new DeleteCommand({
      TableName: TABLE_NAME,
      Key: { PK: `JOB#${jobId}`, SK: "META" },
    })
  );
}

export async function getJob(jobId: string): Promise<Job | null> {
  const result = await docClient.send(
    new GetCommand({
      TableName: TABLE_NAME,
      Key: { PK: `JOB#${jobId}`, SK: "META" },
    })
  );

  if (!result.Item) return null;

  const item = result.Item;
  const job: Job = {
    job_id: jobId,
    status: item.status as JobStatus,
    input_url: item.input_url as string,
    created_at: item.created_at as string,
    updated_at: item.updated_at as string,
  };

  if (item.status === "COMPLETED" && item.generated_llms_txt) {
    job.result = {
      llms_txt: item.generated_llms_txt as string,
      site_title: (item.site_title as string) || "",
      site_summary: (item.site_summary as string) || "",
      pages_analyzed: (item.pages_analyzed as number) || 0,
    };
  }

  if (item.status === "FAILED" && item.error_message) {
    job.error_message = item.error_message as string;
  }

  return job;
}
