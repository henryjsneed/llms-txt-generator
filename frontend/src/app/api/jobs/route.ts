import { NextResponse } from "next/server";
import { v4 as uuidv4 } from "uuid";
import { checkRateLimit, createJob, deleteJob } from "@/lib/aws/dynamo";
import { enqueueJob } from "@/lib/aws/sqs";
import { validateUrl } from "@/lib/url-validation";

export async function POST(request: Request) {
  let body: { url?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body.url || typeof body.url !== "string") {
    return NextResponse.json({ error: "URL is required" }, { status: 400 });
  }

  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded?.split(",")[0]?.trim() || "unknown";
  const allowed = await checkRateLimit(ip);
  if (!allowed) {
    return NextResponse.json(
      { error: "Too many requests. Please wait a minute before trying again." },
      { status: 429 }
    );
  }

  const validation = validateUrl(body.url);
  if (!validation.valid) {
    return NextResponse.json({ error: validation.error }, { status: 400 });
  }

  const jobId = uuidv4();

  let created_at: string;
  try {
    const result = await createJob(jobId, body.url, validation.normalized);
    created_at = result.created_at;
  } catch (err) {
    console.error("Failed to create job in DynamoDB:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  try {
    await enqueueJob(jobId, validation.normalized);
  } catch (err) {
    console.error("Failed to enqueue job to SQS, cleaning up:", err);
    await deleteJob(jobId).catch(() => {});
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }

  return NextResponse.json(
    {
      job_id: jobId,
      status: "PENDING",
      input_url: body.url,
      created_at,
    },
    { status: 202 }
  );
}
