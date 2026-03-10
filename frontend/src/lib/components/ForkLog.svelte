<!-- ForkLog: paginated table of fork events.

     Pagination uses offset/limit: page 0 starts at offset 0, each page
     moves the offset by the page size (50). This is the standard pattern
     for REST pagination — you ask for "50 rows starting at row N."

     The "next" button is disabled when the API returns fewer rows than
     the page size — that signals we've reached the last page.
     No total count is needed; this avoids a separate COUNT(*) query. -->

<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fetchForks, type ForkEvent } from '$lib/api';
  import { sseManager } from '$lib/sse';
  import { truncateHash, formatTimestamp, formatResolution, copyToClipboard } from '$lib/format';

  const PAGE_SIZE = 50;

  let forks: ForkEvent[] = [];
  let page = 0;          // current page number (0-indexed)
  let hasNextPage = false;
  let error: string | null = null;

  async function load() {
    try {
      const data = await fetchForks(page * PAGE_SIZE, PAGE_SIZE);
      forks = data;
      // If the API returned a full page, there might be more
      hasNextPage = data.length === PAGE_SIZE;
      error = null;
    } catch (e) {
      error = 'Failed to load fork events';
    }
  }

  function goNext() {
    page += 1;
    load();
  }

  function goPrev() {
    if (page > 0) {
      page -= 1;
      load();
    }
  }

  let unsubscribe: () => void;

  onMount(() => {
    load();
    sseManager.connect();
    // On SSE update: refresh page 0 if we're on it (new forks land at the top),
    // or just reload the current page (the data may have shifted)
    unsubscribe = sseManager.subscribe(() => {
      load();  // re-fetch current page — keeps pagination state intact
    });
  });

  onDestroy(() => {
    unsubscribe?.();
  });
</script>

{#if error}
  <p style="color: var(--accent-red)">{error}</p>
{:else}
  <div style="overflow-x: auto;">
    <table>
      <thead>
        <tr>
          <th>Height</th>
          <th>Detected</th>
          <th>Orphaned Hash</th>
          <th>Canonical Hash</th>
          <th>Resolution</th>
        </tr>
      </thead>
      <tbody>
        {#each forks as fork (fork.id)}
          <tr>
            <td class="mono">{fork.height.toLocaleString()}</td>
            <td>{formatTimestamp(fork.detected_at)}</td>
            <td class="mono hash-cell">
              <span title={fork.orphaned_hash} style="color: var(--accent-orange)">
                {truncateHash(fork.orphaned_hash)}
              </span>
              <button
                class="copy-btn"
                title="Copy orphaned hash"
                on:click={() => copyToClipboard(fork.orphaned_hash)}
              >⎘</button>
            </td>
            <td class="mono hash-cell">
              <span title={fork.canonical_hash}>
                {truncateHash(fork.canonical_hash)}
              </span>
              <button
                class="copy-btn"
                title="Copy canonical hash"
                on:click={() => copyToClipboard(fork.canonical_hash)}
              >⎘</button>
            </td>
            <td class="mono">{formatResolution(fork.resolution_seconds)}</td>
          </tr>
        {/each}
        {#if forks.length === 0}
          <tr>
            <td colspan="5" style="text-align:center; color: var(--text-secondary); padding: 2rem;">
              No fork events recorded yet.
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>

  <!-- Pagination controls -->
  <div class="pagination">
    <button class="page-btn" on:click={goPrev} disabled={page === 0}>
      &larr; Previous
    </button>
    <span style="color: var(--text-secondary); font-size: 0.8rem;">
      Page {page + 1}
    </span>
    <button class="page-btn" on:click={goNext} disabled={!hasNextPage}>
      Next &rarr;
    </button>
  </div>
{/if}

<style>
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }

  th {
    text-align: left;
    padding: 0.5rem 0.75rem;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }

  td {
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
    white-space: nowrap;
  }

  tr:hover td {
    background: var(--bg-secondary);
  }

  .hash-cell {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .copy-btn {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.85rem;
    padding: 0;
    line-height: 1;
    flex-shrink: 0;
  }

  .copy-btn:hover {
    color: var(--accent-blue);
  }

  .pagination {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 1rem;
    justify-content: flex-start;
  }

  .page-btn {
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-primary);
    padding: 0.35rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
  }

  .page-btn:hover:not(:disabled) {
    border-color: var(--accent-blue);
    color: var(--accent-blue);
  }

  .page-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
