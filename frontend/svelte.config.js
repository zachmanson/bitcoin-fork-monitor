// SvelteKit configuration.
// adapter-static builds to a folder of static HTML/JS/CSS files.
// This means no server-side rendering (SSR) — the app is a pure client-side SPA.
// Why static adapter? FastAPI will serve these files in production. Static files
// are simpler to serve than a Node.js SSR server alongside Python.
import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    adapter: adapter({
      // Output goes to frontend/build/ — FastAPI will serve from here
      pages: 'build',
      assets: 'build',
      fallback: 'index.html',   // SPA fallback: any path serves index.html
    }),
  },
};

export default config;
