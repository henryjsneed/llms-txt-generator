import { SQSClient, SendMessageCommand } from "@aws-sdk/client-sqs";

const client = new SQSClient({
  region: process.env.AWS_REGION || "us-east-1",
});

const QUEUE_URL = process.env.SQS_QUEUE_URL;

export async function enqueueJob(jobId: string, normalizedUrl: string): Promise<void> {
  if (!QUEUE_URL) {
    console.warn(`SQS_QUEUE_URL not set — skipping enqueue for job ${jobId} (local dev mode)`);
    return;
  }

  await client.send(
    new SendMessageCommand({
      QueueUrl: QUEUE_URL,
      MessageBody: JSON.stringify({ job_id: jobId, url: normalizedUrl }),
    })
  );
}
