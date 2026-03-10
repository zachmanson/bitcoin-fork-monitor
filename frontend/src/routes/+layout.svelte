<!-- +layout.svelte wraps every page in the app.
     SvelteKit routes: +layout.svelte is the persistent shell,
     +page.svelte is the content that changes per route.
     Since this is a single-page app with no navigation, the layout
     is minimal — just the CSS import and a header bar. -->
<script>
  import '../app.css';
</script>

<header style="
  padding: 1rem 2rem;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  gap: 0.75rem;
">
  <span style="font-size: 1.25rem; font-weight: 600;">Bitcoin Fork Monitor</span>
  <span style="color: var(--text-secondary); font-size: 0.85rem;">live blockchain analysis</span>
</header>

<main style="max-width: 1400px; margin: 0 auto; padding: 2rem;">
  <slot />
</main>
