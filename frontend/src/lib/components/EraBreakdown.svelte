<!-- EraBreakdown: table of stale rate per 2016-block difficulty era.

     Each era = one difficulty adjustment period = 2016 blocks ≈ 2 weeks.
     This is the most technically precise era boundary because the Bitcoin
     protocol adjusts difficulty exactly every 2016 blocks, not on a calendar.

     Pre-2015 data (eras where height_start < 321000) is flagged
     low_confidence because early orphan data from mempool.space's historical
     API has coverage gaps — not all orphans from 2009-2014 were catalogued.
     The asterisk annotation makes this limitation visible in context. -->

<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchEraBreakdown, type EraBreakdown } from '$lib/api';
  import { formatStaleRate } from '$lib/format';

  let eras: EraBreakdown[] = [];
  let error: string | null = null;

  onMount(async () => {
    try {
      eras = await fetchEraBreakdown();
    } catch (e) {
      error = 'Failed to load era breakdown';
    }
  });
</script>

{#if error}
  <p style="color: var(--accent-red)">{error}</p>
{:else}
  <div style="overflow-x: auto;">
    <table>
      <thead>
        <tr>
          <th>Era</th>
          <th>Height Range</th>
          <th>Canonical</th>
          <th>Orphaned</th>
          <th>Stale Rate</th>
        </tr>
      </thead>
      <tbody>
        {#each eras as era (era.era)}
          <tr class:low-confidence={era.low_confidence}>
            <td class="mono">#{era.era}</td>
            <td class="mono">
              {era.height_start.toLocaleString()}–{era.height_end.toLocaleString()}
              {#if era.low_confidence}
                <!-- Inline annotation: asterisk with tooltip explains why confidence is low -->
                <span
                  class="confidence-note"
                  title="Pre-2015 data: mempool.space historical orphan records have coverage gaps for early blocks. Stale rate may be understated."
                >*</span>
              {/if}
            </td>
            <td class="mono">{era.canonical.toLocaleString()}</td>
            <td class="mono">{era.orphaned.toLocaleString()}</td>
            <td class="mono">{formatStaleRate(era.stale_rate)}</td>
          </tr>
        {/each}
        {#if eras.length === 0}
          <tr>
            <td colspan="5" style="text-align:center; color: var(--text-secondary); padding: 2rem;">
              No era data available yet.
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>

  <!-- Legend for the asterisk annotation -->
  {#if eras.some(e => e.low_confidence)}
    <p class="legend">
      * Pre-2015 data: early orphan records have coverage gaps. Stale rate for these eras may be understated.
    </p>
  {/if}
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
  }

  tr.low-confidence td {
    color: var(--text-secondary);
  }

  tr:hover td {
    background: var(--bg-secondary);
  }

  .confidence-note {
    color: var(--accent-orange);
    margin-left: 0.2rem;
    cursor: help;
    font-size: 0.9rem;
  }

  .legend {
    margin-top: 0.75rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    font-style: italic;
  }
</style>
