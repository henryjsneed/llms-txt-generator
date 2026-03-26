import type { NextConfig } from "next";

import { PRODUCTION_BUILD_REQUIRED_KEYS } from "./src/lib/production-env-keys";

if (process.env.NODE_ENV === "production") {
  for (const key of PRODUCTION_BUILD_REQUIRED_KEYS) {
    if (!process.env[key]) {
      throw new Error(`Missing required environment variable for production build: ${key}`);
    }
  }
}

const nextConfig: NextConfig = {
  env: {
    DYNAMODB_TABLE_NAME: process.env.DYNAMODB_TABLE_NAME,
    SQS_QUEUE_URL: process.env.SQS_QUEUE_URL,
  },
};

export default nextConfig;
