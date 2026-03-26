/** Env vars that must exist for `next build` when NODE_ENV is production */
export const PRODUCTION_BUILD_REQUIRED_KEYS = ["SQS_QUEUE_URL", "DYNAMODB_TABLE_NAME"] as const;
