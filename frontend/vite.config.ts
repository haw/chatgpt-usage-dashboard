/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'

// Client version: package.json's semantic version, plus the first 8 characters of the commit
// being built when the build is told its revision (APP_REVISION), e.g. 1.0.0+6095c825.
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }
const revision = (process.env.APP_REVISION ?? '').trim().slice(0, 8)
const appVersion = revision ? `${version}+${revision}` : version

// Everything the FastAPI backend owns is proxied in development. The Host header is
// passed through (changeOrigin: false) so the OAuth callback URL stays on this origin.
const backend = process.env.VITE_API_PROXY ?? 'http://localhost:8000'
const backendPaths = ['/api', '/login/google', '/auth', '/logout', '/health']

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(appVersion) },
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
