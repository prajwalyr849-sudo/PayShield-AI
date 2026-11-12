/**
 * Client-side validation for merchant (original-merchant handoff) URLs.
 *
 * Mirrors the backend validator (backend/assistant/url_validation.py) so the
 * frontend can reject unsafe merchant links before navigating. The backend
 * re-validates independently; this is a UX guard so users never see a broken
 * or unsafe handoff target.
 *
 * Only well-formed http/https URLs with a real public hostname are accepted.
 * Unsafe schemes (javascript:, data:, file:, ftp: ...), malformed URLs, and
 * localhost/private-address targets are rejected to avoid open-redirect and
 * SSRF risks.
 *
 * This is a structural validator only: it never fetches the target and cannot
 * confirm the merchant is trustworthy or that an order will be accepted.
 */

const _ALLOWED_SCHEMES = new Set(["http", "https"]);

const _LOCAL_HOSTS = new Set([
  "localhost",
  "localhost.localdomain",
]);

export class MerchantUrlError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MerchantUrlError";
  }
}

function _stripIpv6Brackets(hostname: string): string {
  if (hostname.startsWith("[") && hostname.endsWith("]")) {
    return hostname.slice(1, -1);
  }
  return hostname;
}

export function validateMerchantUrl(url: string | null | undefined): string {
  if (!url || typeof url !== "string" || !url.trim()) {
    throw new MerchantUrlError("No merchant URL was provided.");
  }
  url = url.trim();

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new MerchantUrlError("The merchant URL could not be parsed.");
  }

  const scheme = parsed.protocol.replace(/:$/, "").toLowerCase();
  if (!_ALLOWED_SCHEMES.has(scheme)) {
    throw new MerchantUrlError(
      `Unsupported merchant URL scheme '${scheme || 'none'}'. Only http and https merchant links are supported.`
    );
  }

  const hostname = parsed.hostname;
  if (!hostname) {
    throw new MerchantUrlError("The merchant URL has no host and is malformed.");
  }

  // Reject literal IP addresses (IPv4 dotted-quad or IPv6) so a malicious or
  // compromised merchant evidence record cannot redirect the buyer to an
  // internal address (SSRF / open redirect). Merchants are addressed by domain
  // name, never by a raw IP literal.
  const cleanHost = _stripIpv6Brackets(hostname);
  const isIpv4 = /^(\d{1,3}\.){3}\d{1,3}$/.test(cleanHost);
  const isIpv6 = cleanHost.includes(":");
  if (isIpv4 || isIpv6) {
    throw new MerchantUrlError(
      "The merchant URL points to a local or private address."
    );
  }

  const lowerHost = hostname.toLowerCase();
  if (
    _LOCAL_HOSTS.has(lowerHost) ||
    lowerHost.endsWith(".local") ||
    lowerHost.endsWith(".invalid") ||
    lowerHost.endsWith(".test") ||
    lowerHost.endsWith(".example")
  ) {
    throw new MerchantUrlError(
      "The merchant URL points to a local or reserved address."
    );
  }

  return url;
}

export function isValidMerchantUrl(url: string | null | undefined): boolean {
  try {
    validateMerchantUrl(url);
    return true;
  } catch {
    return false;
  }
}
