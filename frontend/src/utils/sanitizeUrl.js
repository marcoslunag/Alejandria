/**
 * Validates that a URL uses http or https protocol.
 * Returns the URL if safe, or '#' (inert) if not.
 * Prevents javascript: XSS and other protocol injection.
 */
export function sanitizeUrl(url) {
  if (!url || typeof url !== 'string') return '#';
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return url;
    }
  } catch {
    // Not a valid absolute URL — could be a relative path, allow it
    if (url.startsWith('/') || url.startsWith('./') || url.startsWith('../')) {
      return url;
    }
  }
  return '#';
}
