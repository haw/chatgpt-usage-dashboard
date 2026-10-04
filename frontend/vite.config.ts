/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { defineConfig } from 'vite'

// The commit HEAD points at, read straight from a .git directory (the container has no git).
function gitHead(gitDir: string): string {
  try {
    const head = readFileSync(join(gitDir, 'HEAD'), 'utf8').trim()
    if (!head.startsWith('ref: ')) return head
    const ref = head.slice('ref: '.length)
    if (existsSync(join(gitDir, ref))) return readFileSync(join(gitDir, ref), 'utf8').trim()
    const packed = readFileSync(join(gitDir, 'packed-refs'), 'utf8').split('\n').find((line) => line.endsWith(` ${ref}`))
    return packed?.split(' ')[0] ?? ''
  } catch {
    return ''
  }
}

// Client version: package.json's semantic version plus the first 8 characters of the commit,
// e.g. 1.0.0+6095c825. A deploy passes its commit in APP_REVISION; in local development
// APP_GIT_DIR points at the mounted repository's .git and HEAD is read when Vite starts.
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }
const revision = ((process.env.APP_REVISION ?? '').trim() || (process.env.APP_GIT_DIR ? gitHead(process.env.APP_GIT_DIR) : '')).slice(0, 8)
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
