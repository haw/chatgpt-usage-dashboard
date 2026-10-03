import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { readFileSync } from 'node:fs'
import { beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { renderApp, useRealBackend } from '../test/mocks'
import IndividualPage from './IndividualPage'
import SettingsPage from './SettingsPage'

const BACKEND = process.env.BACKEND ?? 'http://localhost:8001'

describe('SettingsPage', () => {
  beforeAll(() => useRealBackend())
  beforeEach(() => localStorage.clear())

  it('lists detectors, manages day overrides and saves prompts and limits', async () => {
    localStorage.setItem('chatgpt-dashboard.day-overrides.v1', JSON.stringify({ '2026-09-24': 'holiday' }))
    renderApp(<SettingsPage />)
    await screen.findByText('トークン急増', {}, { timeout: 10_000 })
    expect(screen.getByText('9/24（木）')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '解除' }))
    expect(localStorage.getItem('chatgpt-dashboard.day-overrides.v1')).toBe('{}')
    expect(screen.getByText('手動設定はありません。')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '統計に詳しい人向け' }))
    await userEvent.click(screen.getByRole('button', { name: 'プロンプトを保存' }))
    expect(JSON.parse(localStorage.getItem('chatgpt-dashboard.ai-prompts.v1')!).system).toMatch(/^役割: 統計に慣れた/)

    const five = screen.getByLabelText('5時間上限トークン')
    await userEvent.clear(five)
    await userEvent.type(five, '1000000')
    await userEvent.click(screen.getByRole('button', { name: '設定を保存' }))
    expect(JSON.parse(localStorage.getItem('chatgpt-dashboard.limit-settings.v1')!)).toEqual({ fiveHour: 1_000_000, weekly: 173_000_000 })
  })
})

describe('IndividualPage against the real API', () => {
  beforeAll(async () => {
    useRealBackend()
    // Seed one person from the synthetic tokens fixture (same export format). jsdom's FormData is not
    // understood by Node's fetch, so the multipart body is assembled by hand.
    const boundary = `----vitest${Date.now()}`
    const file = readFileSync('../tests/fixtures/workspace-tokens-2026-09.json', 'utf8')
    const body = [
      `--${boundary}\r\nContent-Disposition: form-data; name="user_label"\r\n\r\ntest@example.com\r\n`,
      `--${boundary}\r\nContent-Disposition: form-data; name="tokens_file"; filename="tokens.json"\r\nContent-Type: application/json\r\n\r\n${file}\r\n`,
      `--${boundary}--\r\n`,
    ].join('')
    const response = await fetch(`${BACKEND}/api/individual/import`, { method: 'POST', headers: { 'Content-Type': `multipart/form-data; boundary=${boundary}` }, body })
    if (!response.ok) throw new Error(`seed failed: ${response.status} ${await response.text()}`)
  })
  beforeEach(() => localStorage.clear())

  it('shows the seeded user with quota estimates and both tables', async () => {
    renderApp(<IndividualPage />)
    await screen.findByText(/test@example.com/, {}, { timeout: 10_000 })
    await waitFor(() => expect(screen.getByText('期間総トークン').nextSibling?.textContent).not.toBe('0'), { timeout: 10_000 })
    expect(screen.getAllByText(/回相当/).length).toBeGreaterThan(0)
    const tables = screen.getAllByRole('table')
    expect(tables.length).toBe(2)
    expect(within(tables[1]).getAllByRole('row').length).toBeGreaterThan(10)
    expect(screen.getAllByTestId('chart').length).toBe(2)
  })
})
