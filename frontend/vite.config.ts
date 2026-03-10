// Vite is the build tool that powers SvelteKit's dev server.
// The proxy config here routes any fetch('/api/...') from the browser
// to FastAPI running at localhost:8000 — this avoids CORS errors during
// development without needing to configure CORS headers on the backend.
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      // Any request to /api/* from the browser is forwarded to FastAPI
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
