<!-- LiveFeed: table of the most recent blocks, newest at top.

     Orphaned blocks are highlighted with a colored row background —
     the is_canonical field drives the visual indicator.

     Feed capacity is capped at 50 rows (matches the API default).
     When a new SSE event arrives, the feed re-fetches /api/blocks and
     prepends any blocks newer than the current top. New blocks "slide in"
     at the top by replacing the full list (simpler and correct for re-orgs
     where previously-canonical blocks may become orphaned). -->

<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fetchBlocks, type Block } from '$lib/api';
  import { sseManager } from '$lib/sse';
  import { truncateHash, formatTimestamp, copyToClipboard } from '$lib/format';

  let blocks: Block[] = [];
  let error: string | null = null;

  async function load() {
    try {
      blocks = await fetchBlocks(50);
      error = null;
    } catch (e) {
      error = 'Failed to load blocks';
    }
  }

  let unsubscribe: () => void;

  onMount(() => {
    load();
    sseManager.connect();
    unsubscribe = sseManager.subscribe(load);
  });

  onDestroy(() => {
    unsubscribe?.();
  });

  async function handleCopy(hash: string) {
    await copyToClipboard(hash);
    // Brief visual feedback (implementation: add a flash class or title change)
  }
</script>

{#if error}
  <p style="color: var(--accent-red)">{error}</p>
{:else}
  <div style="overflow-x: auto;">
    <table>
      <thead>
        <tr>
          <th>Height</th>
          <th>Hash</th>
          <th>Timestamp</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {#each blocks as block (block.hash)}
          <tr class:orphaned={!block.is_canonical}>
            <td class="mono">{block.height.toLocaleString()}</td>
            <td class="mono hash-cell">
              <span title={block.hash}>{truncateHash(block.hash)}</span>
              <button
                class="copy-btn"
                title="Copy full hash"
                on:click={() => handleCopy(block.hash)}
              >&#x2398;</button>
            </td>
            <td>{formatTimestamp(block.timestamp)}</td>
            <td>
              {#if block.is_canonical}
                <span class="badge badge--canonical">canonical</span>
              {:else}
                <span class="badge badge--orphaned">orphaned</span>
              {/if}
            </td>
          </tr>
        {/each}
        {#if blocks.length === 0}
          <tr><td colspan="4" style="text-align:center; color: var(--text-secondary);">Loading blocks...</td></tr>
        {/if}
      </tbody>
    </table>
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
  }

  td {
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
  }

  tr:hover td {
    background: var(--bg-secondary);
  }

  tr.orphaned td {
    background: rgba(240, 136, 62, 0.08);  /* --accent-orange at low opacity */
  }

  tr.orphaned:hover td {
    background: rgba(240, 136, 62, 0.15);
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
  }

  .copy-btn:hover {
    color: var(--accent-blue);
  }

  .badge {
    font-size: 0.7rem;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .badge--canonical {
    background: rgba(63, 185, 80, 0.15);
    color: var(--accent-green);
  }

  .badge--orphaned {
    background: rgba(240, 136, 62, 0.15);
    color: var(--accent-orange);
  }
</style>
