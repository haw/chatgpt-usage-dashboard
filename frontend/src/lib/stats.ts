import type { DailyRow, Signal } from '../api/types'

export function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return 0
  const pos = (sorted.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}

/** The metric a detector judged, read back from a daily row. */
export function metricOf(signal: Signal, row: DailyRow): number | null {
  const p = signal.product
  switch (signal.detector) {
    case 'tokens_per_user':
      return row.tokens && row.active_users && p && row.active_users[p] ? row.tokens[p] / row.active_users[p] : null
    case 'dau_change':
    case 'dau_increase':
      return row.active_users && p ? row.active_users[p] : null
    case 'holiday_usage':
      return row.tokens ? row.tokens.total : null
    default:
      return row.tokens ? (p ? row.tokens[p] : row.tokens.total) : null
  }
}

/** What each detector measures, in plain words (goes into the JSON the AI receives). */
export function plainMetric(signal: Signal): string {
  const p = signal.product ? signal.product.toUpperCase() : '全製品'
  switch (signal.detector) {
    case 'tokens_per_user':
      return `${p}の1人あたり利用量`
    case 'dau_change':
    case 'dau_increase':
      return `${p}の利用者数`
    case 'holiday_usage':
      return '休日の利用量'
    default:
      return `${p}の利用量`
  }
}

export function daysBefore(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}
