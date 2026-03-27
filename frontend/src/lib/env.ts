const isProduction = process.env.NODE_ENV === "production";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function optional(name: string, fallback: string): string {
  return process.env[name] || fallback;
}

export const env = {
  region: optional("AWS_REGION", "us-west-2"),
  tableName: optional("DYNAMODB_TABLE_NAME", "llms-txt-generator"),
  dynamoEndpoint: process.env.DYNAMODB_ENDPOINT || undefined,
  sqsQueueUrl: isProduction ? required("SQS_QUEUE_URL") : process.env.SQS_QUEUE_URL,
} as const;
