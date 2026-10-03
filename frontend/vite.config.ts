/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Everything the FastAPI backend owns is proxied in development. The Host header is
// passed through (changeOrigin: false) so the OAuth callback URL stays on this origin.
const backend = process.env.VITE_API_PROXY ?? 'http://localhost:8000'
const backendPaths = ['/api', '/login/google', '/auth', '/logout', '/health']

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(backendPaths.map((path) => [path, { target: backend, changeOrigin: false }])),
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id: string) => (id.includes('/echarts') ? 'echarts' : id.includes('/@mui/') ? 'mui' : undefined),
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    testTimeout: 20_000,
  },
})
