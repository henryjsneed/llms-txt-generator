const BLOCKED_HOSTS = new Set([
  "localhost",
  "127.0.0.1",
  "[::1]",
  "0.0.0.0",
  "169.254.169.254",
  "metadata.google.internal",
]);

export function validateUrl(raw: string): { valid: true; normalized: string } | { valid: false; error: string } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { valid: false, error: "URL is required" };
  }

  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return { valid: false, error: "Invalid URL format" };
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { valid: false, error: "Only http and https URLs are allowed" };
  }

  const hostname = url.hostname.toLowerCase();
  if (BLOCKED_HOSTS.has(hostname)) {
    return { valid: false, error: "This host is not allowed" };
  }

  if (/^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)/.test(hostname)) {
    return { valid: false, error: "Private IP addresses are not allowed" };
  }

  url.hash = "";
  let normalized = url.toString();
  if (normalized.endsWith("/") && url.pathname === "/") {
    normalized = normalized.slice(0, -1);
  }

  return { valid: true, normalized };
}
