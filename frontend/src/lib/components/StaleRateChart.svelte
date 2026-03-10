<!-- StaleRateChart: line chart of stale rate over time.
     Built with Lightweight Charts v5 — a professional-grade financial
     charting library well-suited to time-series data.

     Why Lightweight Charts instead of a CSS chart or Chart.js?
     It handles large datasets efficiently (880k blocks → ~1000 monthly
     buckets), has a clean dark theme, and is designed for time-series.

     The chart renders into a DOM element via createChart(). In Svelte,
     we get the DOM reference using bind:this on the container div.
     bind:this is Svelte's way of reading a reference to a real DOM node,
     equivalent to document.getElementById() but reactive. -->

<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createChart, LineSeries } from 'lightweight-charts';
  import { fetchStaleRateOverTime, type StaleRatePoint } from '$lib/api';
  import { sseManager } from '$lib/sse';

  // period is the current toggle state
  let period: 'weekly' | 'monthly' = 'monthly';
  let container: HTMLDivElement;
  let chart: ReturnType<typeof createChart> | null = null;
  let lineSeries: ReturnType<typeof chart.addSeries> | null = null;
  let error: string | null = null;

  // Convert "YYYY-MM" → "YYYY-MM-01" for Lightweight Charts time axis
  // Convert "YYYY-W01" → the Monday date string for that ISO week
  function toChartTime(periodStr: string): string {
    if (periodStr.includes('W')) {
      // ISO week: "2024-W03" → parse to date of that Monday
      const [year, week] = periodStr.split('-W');
      const jan4 = new Date(Number(year), 0, 4); // Jan 4 is always in week 1
      const dayOfWeek = jan4.getDay() || 7; // Monday = 1
      const weekStart = new Date(jan4);
      weekStart.setDate(jan4.getDate() - (dayOfWeek - 1) + (Number(week) - 1) * 7);
      return weekStart.toISOString().slice(0, 10);
    }
    // Monthly "YYYY-MM" → "YYYY-MM-01"
    return `${periodStr}-01`;
  }

  function buildChartData(points: StaleRatePoint[]) {
    // Lightweight Charts requires data sorted by time ascending
    return points
      .map(p => ({
        time: toChartTime(p.period),
        value: parseFloat((p.stale_rate * 100).toFixed(4)),  // percentage
      }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }

  async function load() {
    try {
      const data = await fetchStaleRateOverTime(period);
      if (lineSeries) {
        lineSeries.setData(buildChartData(data));
        chart?.timeScale().fitContent();
      }
      error = null;
    } catch (e) {
      error = 'Failed to load stale rate data';
    }
  }

  // Debounce: collapse rapid SSE bursts (e.g. during backfill) into one reload.
  // Without this, each incoming block during backfill would trigger a full table scan.
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  function debouncedLoad() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(load, 10_000);
  }

  let unsubscribe: () => void;

  onMount(() => {
    // createChart() attaches to the container div and returns a chart instance.
    // The options configure the visual appearance — dark theme to match the dashboard.
    chart = createChart(container, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#8b949e',  // --text-secondary
      },
      grid: {
        vertLines: { color: '#30363d' },  // --border
        horzLines: { color: '#30363d' },
      },
      timeScale: {
        borderColor: '#30363d',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: '#30363d',
      },
      width: container.clientWidth,
      height: 300,
      handleScroll: true,
      handleScale: true,
    });

    // addSeries() creates a line series on the chart.
    // LineSeries is the correct type for a continuous trend line.
    lineSeries = chart.addSeries(LineSeries, {
      color: '#58a6ff',   // --accent-blue
      lineWidth: 2,
      priceFormat: {
        type: 'custom',
        formatter: (value: number) => `${value.toFixed(3)}%`,
      },
    });

    load();

    sseManager.connect();
    unsubscribe = sseManager.subscribe(debouncedLoad);

    // Resize chart when window size changes
    const observer = new ResizeObserver(() => {
      chart?.applyOptions({ width: container.clientWidth });
    });
    observer.observe(container);

    return () => observer.disconnect();
  });

  onDestroy(() => {
    unsubscribe?.();
    if (debounceTimer) clearTimeout(debounceTimer);
    chart?.remove();  // important: clean up the WebGL canvas
  });

  function togglePeriod(newPeriod: 'weekly' | 'monthly') {
    period = newPeriod;
    load();
  }
</script>

<div style="display: flex; flex-direction: column; gap: 1rem;">
  <!-- Period toggle buttons -->
  <div style="display: flex; gap: 0.5rem; align-items: center;">
    <span style="color: var(--text-secondary); font-size: 0.8rem;">Aggregation:</span>
    <button
      class="toggle-btn"
      class:active={period === 'monthly'}
      on:click={() => togglePeriod('monthly')}
    >Monthly</button>
    <button
      class="toggle-btn"
      class:active={period === 'weekly'}
      on:click={() => togglePeriod('weekly')}
    >Weekly</button>
  </div>

  {#if error}
    <p style="color: var(--accent-red)">{error}</p>
  {/if}
  <!-- Container stays in DOM at all times so bind:this is never null.
       Hidden via CSS when the error state is active. -->
  <div
    bind:this={container}
    style="background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; {error ? 'display: none' : ''}"
  ></div>
</div>

<style>
  .toggle-btn {
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text-secondary);
    padding: 0.25rem 0.6rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
  }

  .toggle-btn.active {
    border-color: var(--accent-blue);
    color: var(--accent-blue);
  }

  .toggle-btn:hover:not(.active) {
    color: var(--text-primary);
  }
</style>
