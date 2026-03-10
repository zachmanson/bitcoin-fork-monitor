<!-- The main dashboard page.
     All four sections appear here in a single vertical scroll:
     stats → live feed → fork log → analytics charts.
     Each section will be filled in by Plans 02, 03, and 04.
     For now, placeholder headings confirm the layout is wired. -->
<script>
  // Sections will import components as plans complete.
  // This shell confirms routing and layout work before any real UI is added.
</script>

<svelte:head>
  <title>Bitcoin Fork Monitor</title>
</svelte:head>

<div style="display: flex; flex-direction: column; gap: 3rem;">

  <section id="stats">
    <h2 style="margin-bottom: 1rem; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em;">Summary Stats</h2>
    <p style="color: var(--text-secondary);">[ Stats panel — Plan 02 ]</p>
  </section>

  <section id="live-feed">
    <h2 style="margin-bottom: 1rem; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em;">Live Block Feed</h2>
    <p style="color: var(--text-secondary);">[ Live feed — Plan 02 ]</p>
  </section>

  <section id="fork-log">
    <h2 style="margin-bottom: 1rem; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em;">Fork Event Log</h2>
    <p style="color: var(--text-secondary);">[ Fork event log — Plan 03 ]</p>
  </section>

  <section id="analytics">
    <h2 style="margin-bottom: 1rem; color: var(--text-secondary); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em;">Analytics</h2>
    <p style="color: var(--text-secondary);">[ Charts — Plan 04 ]</p>
  </section>

</div>
