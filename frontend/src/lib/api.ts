// API client for bitcoin-fork-monitor backend.
//
// Why wrapper functions instead of raw fetch() calls in components?
// Centralizing the URL strings and response types here means:
//   1. If an endpoint URL changes, you fix it in one place.
//   2. TypeScript types are defined once and shared everywhere.
//   3. Components stay focused on rendering, not data fetching.

export interface Block {
  hash: string;
  height: number;
  timestamp: string;   // ISO 8601 UTC string from FastAPI
  is_canonical: boolean;
}

export interface Stats {
  canonical_blocks: number;
  orphaned_blocks: number;
  stale_rate: number;      // [0.0, 1.0]
  last_fork_at: string | null;
}

export interface ForkEvent {
  id: number;
  height: number;
  canonical_hash: string;
  orphaned_hash: string;
  detected_at: string;            // ISO 8601 UTC
  resolution_seconds: number | null;
}

export interface StaleRatePoint {
  period: string;   // "YYYY-MM" or "YYYY-W01"
  canonical: number;
  orphaned: number;
  stale_rate: number;
}

export interface EraBreakdown {
  era: number;
  height_start: number;
  height_end: number;
  canonical: number;
  orphaned: number;
  stale_rate: number;
  low_confidence: boolean;
}

export async function fetchBlocks(limit = 50): Promise<Block[]> {
  const res = await fetch(`/api/blocks?limit=${limit}`);
  if (!res.ok) throw new Error(`/api/blocks returned ${res.status}`);
  return res.json();
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch('/api/stats');
  if (!res.ok) throw new Error(`/api/stats returned ${res.status}`);
  return res.json();
}

export async function fetchForks(offset = 0, limit = 50): Promise<ForkEvent[]> {
  const res = await fetch(`/api/forks?offset=${offset}&limit=${limit}`);
  if (!res.ok) throw new Error(`/api/forks returned ${res.status}`);
  return res.json();
}

export async function fetchStaleRateOverTime(period: 'weekly' | 'monthly' = 'monthly'): Promise<StaleRatePoint[]> {
  const res = await fetch(`/api/analytics/stale-rate-over-time?period=${period}`);
  if (!res.ok) throw new Error(`/api/analytics/stale-rate-over-time returned ${res.status}`);
  return res.json();
}

export async function fetchEraBreakdown(): Promise<EraBreakdown[]> {
  const res = await fetch('/api/analytics/era-breakdown');
  if (!res.ok) throw new Error(`/api/analytics/era-breakdown returned ${res.status}`);
  return res.json();
}
