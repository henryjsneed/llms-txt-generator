import { NextResponse } from "next/server";
import { getJob } from "@/lib/aws/dynamo";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  if (!id || typeof id !== "string") {
    return NextResponse.json({ error: "Job ID is required" }, { status: 400 });
  }

  try {
    const job = await getJob(id);
    if (!job) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }
    return NextResponse.json(job, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    console.error("Failed to get job:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
