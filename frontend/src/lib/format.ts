// Display formatting utilities.
//
// These functions translate raw API values into the display strings
// specified in the project context. Centralizing them means every
// component renders the same format — no inconsistencies.

/**
 * Truncate a block hash to first 8 + last 8 characters.
 * Example: "0000abc1...ff2d3e4f"
 */
export function truncateHash(hash: string): string {
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}...${hash.slice(-8)}`;
}

/**
 * Format an ISO datetime string as "YYYY-MM-DD HH:MM UTC".
 * Example: "2024-01-15 14:32 UTC"
 */
export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`
  );
}

/**
 * Format a stale rate float [0.0, 1.0] as a percentage string.
 * Example: 0.0042 -> "0.42%"
 */
export function formatStaleRate(rate: number): string {
  return `${(rate * 100).toFixed(2)}%`;
}

/**
 * Format resolution time in seconds.
 * Example: 12.345 -> "12.3s", null -> "—"
 */
export function formatResolution(seconds: number | null): string {
  if (seconds === null) return '\u2014';
  return `${seconds.toFixed(1)}s`;
}

/**
 * Copy text to clipboard. Returns a promise that resolves to true on success.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
