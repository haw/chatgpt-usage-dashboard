import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { Route, Routes } from 'react-router-dom'

import { renderApp, useRealBackend } from '../test/mocks'
import InsightsPage from './InsightsPage'

function renderInsights(route = '/insights') {
  return renderApp(
    <Routes>
      <Route path="/insights" element={<InsightsPage />} />
      <Route path="/insights/:date" element={<InsightsPage />} />
    </Routes>,
    { route },
  )
}

describe('InsightsPage against the real API', () => {
  beforeAll(() => useRealBackend())
  beforeEach(() => localStorage.clear())

  it('lists ranked days with their observations', async () => {
    renderInsights()
    await screen.findByText(/最終データ日/, {}, { timeout: 10_000 })
    const priority = screen.getByText('優先して確認').closest('div')!.parentElement!.parentElement!
    const cards = within(priority).getAllByText('グラフで見る')
    expect(cards.length).toBeGreaterThan(0)
    expect(screen.getAllByText(/判定ライン/).length).toBeGreaterThan(0)
  })

  it('marks a day as checked and back', async () => {
    renderInsights()
    await screen.findByText(/最終データ日/, {}, { timeout: 10_000 })
    const [first] = screen.getAllByText('確認済みにする')
    const card = first.closest('.MuiPaper-root') as HTMLElement
    const date = within(card).getByText(/^\d+\/\d+（.）$/).textContent
    await userEvent.click(first)
    await waitFor(() => expect(screen.getByText(/確認済み \d+日をすべて解除/)).toBeInTheDocument(), { timeout: 10_000 })
    await userEvent.click(screen.getByText(/確認済み \d+日をすべて解除/))
    await waitFor(() => expect(screen.queryByText(/確認済み \d+日をすべて解除/)).not.toBeInTheDocument(), { timeout: 10_000 })
    expect(screen.getAllByText(date!).length).toBeGreaterThan(0)
  })

  it('opens the observation panel from a deep link and shows one chart per observation', async () => {
    renderInsights()
    await screen.findByText(/最終データ日/, {}, { timeout: 10_000 })
    await userEvent.click(screen.getAllByText('グラフで見る')[0])
    const dialog = await screen.findByRole('dialog', {}, { timeout: 10_000 })
    await waitFor(() => expect(within(dialog).getAllByTestId('chart').length).toBeGreaterThan(0), { timeout: 10_000 })
    expect(within(dialog).getByText('AIに問い合わせる')).toBeDisabled()  // no WebGPU / built-in model in jsdom
    await userEvent.click(within(dialog).getByRole('button', { name: '両方' }))
    await waitFor(() => expect(within(dialog).getAllByTestId('chart').length).toBeGreaterThanOrEqual(2))
    expect(localStorage.getItem('chatgpt-dashboard.context-mode.v1')).toBe('both')
  })
})
