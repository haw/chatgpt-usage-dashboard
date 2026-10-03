import type { IndividualRow, ProductValues } from '../api/types'
import type { Limits } from '../state/viewer'

/** Monday of the week containing the date. */
export function weekStart(date: string): string {
  const value = new Date(`${date}T00:00:00Z`)
  const offset = (value.getUTCDay() + 6) % 7
  value.setUTCDate(value.getUTCDate() - offset)
  return value.toISOString().slice(0, 10)
}

export interface WeeklyRow extends ProductValues {
  start: string
  end: string
  total: number
  agentTokens: number
}

export function buildWeeklyRows(rows: IndividualRow[]): WeeklyRow[] {
  const grouped = new Map<string, WeeklyRow>()
  rows.forEach((row) => {
    const start = weekStart(row.date)
    const current = grouped.get(start) ?? { start, end: '', chat: 0, codex: 0, work: 0, total: 0, agentTokens: 0 }
    current.chat += row.tokens.chat
    current.codex += row.tokens.codex
    current.work += row.tokens.work
    current.total += row.tokens.total
    grouped.set(start, current)
  })
  return [...grouped.values()]
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((row) => {
      const end = new Date(`${row.start}T00:00:00Z`)
      end.setUTCDate(end.getUTCDate() + 6)
      return { ...row, end: end.toISOString().slice(0, 10), agentTokens: row.codex + row.work }
    })
}

export interface LimitInfo {
  ratio: number
  status: 'reached' | 'near' | 'normal'
  label: string
}

export function limitInfo(value: number, limit: number): LimitInfo {
  const ratio = (value / limit) * 100
  const hits = Math.floor(value / limit)
  if (hits > 0) return { ratio, status: 'reached', label: `${hits}回相当` }
  if (ratio >= 80) return { ratio, status: 'near', label: '80%以上' }
  return { ratio, status: 'normal', label: '未到達目安' }
}

export interface QuotaEstimate {
  fiveHourHits: number
  weeklyHits: number
  pressureWeeks: number
  level: '低' | '中' | '高'
  reason: string
}

/** Rough "how often did this person hit the Codex+Work quotas" estimate from daily totals. */
export function quotaEstimate(rows: IndividualRow[], limits: Limits): QuotaEstimate {
  const fiveHourHits = rows.reduce((sum, row) => sum + Math.floor((row.tokens.codex + row.tokens.work) / limits.fiveHour), 0)
  const weeks = buildWeeklyRows(rows).map((row) => row.agentTokens)
  const weeklyHits = weeks.reduce((sum, value) => sum + Math.floor(value / limits.weekly), 0)
  const pressureWeeks = weeks.filter((value) => value >= limits.weekly * 0.8).length
  const maxWeeklyRatio = weeks.length ? Math.max(...weeks) / limits.weekly : 0
  if (weeklyHits > 0 || fiveHourHits >= 2) return { fiveHourHits, weeklyHits, pressureWeeks, level: '高', reason: '利用枠へ繰り返し接近・到達した可能性があります' }
  if (fiveHourHits > 0 || pressureWeeks > 0 || maxWeeklyRatio >= 0.6) return { fiveHourHits, weeklyHits, pressureWeeks, level: '中', reason: '利用枠へ接近した可能性があります' }
  return { fiveHourHits, weeklyHits, pressureWeeks, level: '低', reason: '参考上限の80%未満です' }
}
