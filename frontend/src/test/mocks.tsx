import { ThemeProvider } from '@mui/material'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import { AuthProvider } from '../state/auth'
import { ViewerProvider } from '../state/viewer'
import { theme } from '../theme'

// ECharts needs a canvas; jsdom has none, so charts render as placeholders that expose their option.
vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: unknown }) => <div data-testid="chart" data-option={JSON.stringify(option)} />,
}))

export function renderApp(ui: ReactNode, { route = '/' }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>
            <ViewerProvider>{ui}</ViewerProvider>
          </AuthProvider>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

/** Route fetch() to a real backend (BACKEND env, default http://localhost:8000) so tests exercise the real API shapes. */
export function useRealBackend() {
  const base = process.env.BACKEND ?? 'http://localhost:8000'
  const realFetch = globalThis.fetch
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' && input.startsWith('/') ? base + input : input
    return realFetch(url, init)
  })
}
