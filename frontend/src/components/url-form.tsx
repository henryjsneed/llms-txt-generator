"use client";

import { useRouter } from "next/navigation";
import { useState, type SubmitEvent } from "react";

export default function UrlForm() {
  const [protocol, setProtocol] = useState<"https://" | "http://">("https://");
  const [urlInput, setUrlInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const trimmed = urlInput.trim();
    const hasScheme = /^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//.test(trimmed);
    let normalizedUrl: string;

    if (hasScheme) {
      const schemeMatch = trimmed.match(/^([a-zA-Z][a-zA-Z\d+\-.]*):\/\//);
      const scheme = schemeMatch?.[1]?.toLowerCase();
      if (scheme !== "http" && scheme !== "https") {
        setError("Only http and https URLs are allowed");
        setLoading(false);
        return;
      }
      normalizedUrl = trimmed;
    } else {
      normalizedUrl = `${protocol}${trimmed}`;
    }

    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedUrl }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Something went wrong");
        return;
      }

      if (!data.job_id) {
        setError("Unexpected response from server. Please try again.");
        return;
      }

      router.push(`/jobs/${data.job_id}`);
    } catch {
      setError("Failed to submit. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-xl mx-auto">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <label htmlFor="site-protocol" className="sr-only">
            Protocol
          </label>
          <select
            id="site-protocol"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as "https://" | "http://")}
            className="flex-none min-w-[110px] px-3 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg"
            aria-label="Protocol (http/https)"
          >
            <option value="https://">https://</option>
            <option value="http://">http://</option>
          </select>
          <label htmlFor="site-url" className="sr-only">Website URL</label>
          <input
            id="site-url"
            type="text"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="example.com"
            required
            className="flex-1 min-w-0 px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-lg"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium rounded-lg transition-colors text-lg cursor-pointer disabled:cursor-not-allowed"
          >
            {loading ? "Submitting..." : "Generate"}
          </button>
        </div>

        {error && (
          <p className="text-red-500 text-sm">{error}</p>
        )}
      </form>
    </div>
  );
}
