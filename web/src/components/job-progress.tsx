"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Job } from "@/lib/types";
import ResultView from "./result-view";

const STATUS_TEXT: Record<string, string> = {
  PENDING: "Waiting for worker...",
  RUNNING: "Crawling and analyzing pages...",
};

const MAX_POLL_DURATION_MS = 5 * 60 * 1000; // 5 minutes

export default function JobProgress({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const startedAt = Date.now();

    async function poll() {
      if (Date.now() - startedAt > MAX_POLL_DURATION_MS) {
        setError("This is taking longer than expected. Please try again later.");
        clearInterval(timer);
        return;
      }

      try {
        const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
        if (!res.ok) {
          if (res.status === 404) {
            setError("Job not found. It may have expired.");
            clearInterval(timer);
          } else {
            setError("Failed to fetch job status.");
          }
          return;
        }
        const data: Job = await res.json();
        if (active) {
          setJob(data);
          setError("");
          if (data.status === "COMPLETED" || data.status === "FAILED") {
            clearInterval(timer);
          }
        }
      } catch {
        if (active) setError("Connection error. Retrying...");
      }
    }

    const timer = setInterval(poll, 2000);
    poll();

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [jobId]);

  if (error && !job) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 text-lg">{error}</p>
        <Link href="/" className="mt-4 inline-block text-blue-600 hover:underline">
          Try another URL
        </Link>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="text-center py-12">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" role="status" aria-label="Loading" />
        <p className="mt-4 text-gray-500" aria-live="polite">Loading...</p>
      </div>
    );
  }

  if (job.status === "PENDING" || job.status === "RUNNING") {
    return (
      <div className="text-center py-12">
        <div className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" role="status" aria-label="Processing" />
        <p className="mt-4 text-lg text-gray-600 dark:text-gray-300" aria-live="polite">
          {STATUS_TEXT[job.status]}
        </p>
        <p className="mt-2 text-sm text-gray-400">
          Analyzing <span className="font-mono">{job.input_url}</span>
        </p>
      </div>
    );
  }

  if (job.status === "FAILED") {
    return (
      <div className="text-center py-12">
        <div className="inline-flex items-center gap-2 text-red-500 text-lg">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Generation failed
        </div>
        <p className="mt-2 text-gray-500">{job.error_message || "An unknown error occurred."}</p>
        <Link href="/" className="mt-4 inline-block text-blue-600 hover:underline">
          Try another URL
        </Link>
      </div>
    );
  }

  return <ResultView job={job} />;
}
