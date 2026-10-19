import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// API paths that share a prefix with a React Router client route (/audit vs
// /audit-logs, /settings, /receipts). Browser navigations request text/html
// and must fall through to the SPA; API calls send Accept: application/json
// and are proxied to the backend.
const spaBypass = (req) =>
  (req.headers.accept || '').includes('text/html') ? '/index.html' : undefined

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/check-payment': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/paypal': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/audit': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        bypass: spaBypass,
      },
      '/integrations': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/status': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/recommendations': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/chat': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/products': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/checkout': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/rate': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/guard-buy': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistant/provider-health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/settings': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        bypass: spaBypass,
      },
      '/receipts': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        bypass: spaBypass,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    // '/audit', '/settings' and '/receipts' share a prefix with a client route,
    // so their proxies use spaBypass: a hard navigation/refresh serves the SPA
    // while API calls (Accept: application/json) still reach the backend.
    fallback: 'index.html',
  },
})
