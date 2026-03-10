<script>
  import StatsPanel from '$lib/components/StatsPanel.svelte';
  import LiveFeed from '$lib/components/LiveFeed.svelte';
  import ForkLog from '$lib/components/ForkLog.svelte';
  import StaleRateChart from '$lib/components/StaleRateChart.svelte';
  import EraBreakdown from '$lib/components/EraBreakdown.svelte';
</script>

<svelte:head>
  <title>Bitcoin Fork Monitor</title>
</svelte:head>

<div style="display: flex; flex-direction: column; gap: 3rem;">

  <section id="stats">
    <h2 class="section-heading">Summary Stats</h2>
    <StatsPanel />
  </section>

  <section id="live-feed">
    <h2 class="section-heading">Live Block Feed</h2>
    <LiveFeed />
  </section>

  <section id="fork-log">
    <h2 class="section-heading">Fork Event Log</h2>
    <ForkLog />
  </section>

  <section id="analytics">
    <h2 class="section-heading">Stale Rate Over Time</h2>
    <StaleRateChart />

    <h2 class="section-heading" style="margin-top: 2.5rem;">Era Breakdown</h2>
    <EraBreakdown />
  </section>

</div>

<style>
  .section-heading {
    margin-bottom: 1rem;
    color: var(--text-secondary);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 500;
  }
</style>
