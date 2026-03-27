import { SQSClient, SendMessageCommand } from "@aws-sdk/client-sqs";
import { env } from "../env";

const client = new SQSClient({
  region: env.region,
});

export async function enqueueJob(jobId: string, normalizedUrl: string): Promise<void> {
  if (!env.sqsQueueUrl) {
    console.warn(`SQS_QUEUE_URL not set — skipping enqueue for job ${jobId} (local dev mode)`);
    return;
  }

  await client.send(
    new SendMessageCommand({
      QueueUrl: env.sqsQueueUrl,
      MessageBody: JSON.stringify({ job_id: jobId, url: normalizedUrl }),
    })
  );
}
