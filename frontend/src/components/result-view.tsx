"use client";

import type { Job } from "@/lib/types";
import Link from "next/link";
import { useState } from "react";

export default function ResultView({ job }: { job: Job }) {
  const [copied, setCopied] = useState(false);

  if (!job.result) return null;

  const { llms_txt, site_title, pages_analyzed } = job.result;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(llms_txt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  function handleDownload() {
    const blob = new Blob([llms_txt], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "llms.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            {site_title || job.input_url}
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            {pages_analyzed} pages analyzed
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Link
            href="/"
            className="inline-flex min-w-[12rem] justify-center rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            Generate another
          </Link>
          <button
            onClick={handleCopy}
            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer"
          >
            {copied ? "Copied!" : "Copy to Clipboard"}
          </button>
          <button
            onClick={handleDownload}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors cursor-pointer"
          >
            Download .txt
          </button>
        </div>
      </div>

      <div className="relative rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 text-xs text-gray-500 font-mono">
          llms.txt
        </div>
        <pre className="p-4 overflow-x-auto text-sm leading-relaxed text-gray-800 dark:text-gray-200 whitespace-pre-wrap">{llms_txt}</pre>
      </div>

    </div>
  );
}
