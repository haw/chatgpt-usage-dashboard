import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { renderApp, useRealBackend } from '../test/mocks'
import TrendsPage from './TrendsPage'

// These tests talk to a running backend (AUTH_MODE=none) loaded with the September fixture.
describe('TrendsPage against the real API', () => {
  beforeAll(() => useRealBackend())
  beforeEach(() => localStorage.clear())

  it('renders KPIs, charts, the detected-days list and the daily table', async () => {
    renderApp(<TrendsPage />)
    await waitFor(() => expect(screen.getByText('最新日の製品別最大DAU').nextSibling?.textContent).not.toBe('—'), { timeout: 10_000 })
    expect(screen.getAllByTestId('chart').length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText(/現在の判定で検出された日: \d+日/)).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row').length).toBeGreaterThan(10)
    expect(within(table).getAllByText(/休日/).length).toBeGreaterThan(0)
  })

  it('moving the sensitivity re-queries and explains what changed', async () => {
    renderApp(<TrendsPage />)
    await screen.findByText(/現在の判定で検出された日/, {}, { timeout: 10_000 })
    const slider = screen.getByRole('slider', { name: /感度/ })
    slider.focus()
    await userEvent.keyboard('{ArrowRight}{ArrowRight}')
    await screen.findByText(/感度を 標準 → 高 に変更: 検出 \d+日/, {}, { timeout: 10_000 })
    expect(screen.getByText(/判定: 標準偏差×1\.75/)).toBeInTheDocument()
  })

  it('clicking a date toggles its day kind through the viewer overrides', async () => {
    renderApp(<TrendsPage />)
    await screen.findByRole('table', {}, { timeout: 10_000 })
    const dateCell = () => within(screen.getByRole('table')).getByText(/^2026-09-24/)
    const rowText = () => dateCell().closest('tr')!.textContent ?? ''
    await waitFor(() => expect(rowText()).toMatch(/平日暦/))
    await userEvent.click(dateCell())
    await waitFor(() => expect(rowText()).toMatch(/休日手動/), { timeout: 10_000 })
    expect(JSON.parse(localStorage.getItem('chatgpt-dashboard.day-overrides.v1')!)).toEqual({ '2026-09-24': 'holiday' })
    await userEvent.click(dateCell())
    await waitFor(() => expect(JSON.parse(localStorage.getItem('chatgpt-dashboard.day-overrides.v1')!)).toEqual({}), { timeout: 10_000 })
  })
})
