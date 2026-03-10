<!-- StatsPanel: 4 stat cards showing aggregate dashboard numbers.

     Data flow:
       1. Component mounts -> fetches /api/stats
       2. SSE "update" arrives -> re-fetches /api/stats

     This design avoids polling: data refreshes only when the backend
     signals a change, not on a timer. The SSE connection is shared
     from sseManager — not a new connection per component. -->

<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fetchStats, type Stats } from '$lib/api';
  import { sseManager } from '$lib/sse';
  import { formatStaleRate, formatTimestamp } from '$lib/format';

  let stats: Stats | null = null;
  let error: string | null = null;

  async function load() {
    try {
      stats = await fetchStats();
      error = null;
    } catch (e) {
      error = 'Failed to load stats';
    }
  }

  let unsubscribe: () => void;

  onMount(() => {
    load();
    sseManager.connect();
    // Re-fetch stats whenever a new block/fork event arrives via SSE
    unsubscribe = sseManager.subscribe(load);
  });

  onDestroy(() => {
    unsubscribe?.();
  });
</script>

{#if error}
  <p style="color: var(--accent-red)">{error}</p>
{:else}
  <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;">
    <div class="stat-card">
      <div class="stat-label">Canonical Blocks</div>
      <div class="stat-value">{stats?.canonical_blocks?.toLocaleString() ?? '...'}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Orphaned Blocks</div>
      <div class="stat-value" style="color: var(--accent-orange)">{stats?.orphaned_blocks?.toLocaleString() ?? '...'}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Stale Rate</div>
      <div class="stat-value">{stats ? formatStaleRate(stats.stale_rate) : '...'}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Last Fork</div>
      <div class="stat-value stat-value--small">{stats?.last_fork_at ? formatTimestamp(stats.last_fork_at) : 'None recorded'}</div>
    </div>
  </div>
{/if}

<style>
  .stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1.25rem 1.5rem;
  }
  .stat-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
  }
  .stat-value {
    font-size: 1.75rem;
    font-weight: 600;
    font-family: var(--font-mono);
  }
  .stat-value--small {
    font-size: 0.9rem;
    font-weight: 400;
  }
</style>
