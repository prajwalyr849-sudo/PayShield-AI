import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

// API path prefixes that should be proxied to the backend.
// Frontend routes (e.g. /audit-investigation, /settings, /integrations) must
// NOT match these, otherwise Vite will proxy browser navigation to the
// backend and return 404/401 instead of serving the SPA.
const API_PATHS = [
  '/health',
  '/budget/state',
  '/audit/history',
  '/audit/elastic',
  '/transactions/activity',
  '/receipts',
  '/assistant',
  '/auth',
  '/check-payment',
  '/paypal',
  '/settings/preferences',
];

const isApiPath = (path: string): boolean =>
  API_PATHS.some((prefix) => path === prefix || path.startsWith(prefix + '/'));

// Bypass the proxy for browser navigation requests so Vite serves the SPA.
// API calls from the frontend send Accept: application/json; page loads
// send text/html or no Accept header. We bypass the proxy for anything
// that doesn't explicitly request JSON.
function spaBypass(req: any): any {
  const accept = req.headers.accept || '';
  if (accept.includes('application/json')) {
    return undefined; // Let the proxy handle API calls
  }
  return '/index.html'; // Serve the SPA for browser navigation
}

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
      // Serve index.html for SPA routes that don't match static files or API proxies
      fallback: 'index.html',
      proxy: [
        {
          context: isApiPath,
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          bypass: spaBypass,
        },
      ] as any,
    },
  };
});
