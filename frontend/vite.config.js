import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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
      },
      '/integrations': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
