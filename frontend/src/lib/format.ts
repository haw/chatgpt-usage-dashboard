import type { DayKind, DayKindSource, Signal } from '../api/types'

const numberFormat = new Intl.NumberFormat('ja-JP')
const compactFormat = new Intl.NumberFormat('ja-JP', { notation: 'compact', maximumFractionDigits: 1 })

export const fmt = (value: number): string => numberFormat.format(value)
export const compact = (value: number): string => compactFormat.format(value)
export const formatOptional = (value: number | null | undefined): string => (value == null ? '—' : fmt(value))

const WEEKDAYS = ['日', '月', '火', '水', '木', '金', '土']

export function weekdayOf(date: string): { label: string; day: number } {
  const day = new Date(`${date}T00:00:00Z`).getUTCDay()
  return { label: WEEKDAYS[day], day }
}

/** "9/22（火）" */
export function dateLabel(date: string): string {
  const d = new Date(`${date}T00:00:00Z`)
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}（${WEEKDAYS[d.getUTCDay()]}）`
}

export function kindLabel(kind: DayKind, source?: DayKindSource): string {
  if (kind !== 'holiday') return '平日'
  if (source === 'inferred') return '休日（推定）'
  if (source === 'override') return '休日（手動）'
  return '休日'
}

export const sourceLabel: Record<DayKindSource, string> = { weekend: '週末', weekday: '暦', inferred: '推定', override: '手動' }

export function productName(product: Signal['product']): string {
  return product ? product.toUpperCase() : '全製品'
}

function sdText(score: number | null): string {
  if (score == null) return ''
  const abs = Math.abs(score)
  return `・標準偏差×${abs >= 10 ? Math.round(abs) : abs.toFixed(1)}`
}

function ratioText(value: number, baseline: number | null, kind: DayKind, score: number | null): string {
  if (baseline == null) return ''
  if (!baseline) return kind === 'holiday' ? '（休日なのに利用）' : '（普段は利用なし）'
  const ratio = value / baseline
  return `（普段 ${compact(baseline)} の ${ratio >= 10 ? Math.round(ratio) : ratio.toFixed(1)}倍${sdText(score)}）`
}

/** A level shift is reported by the detector that watches the series, but it is its own kind of observation. */
export function isLevelShift(a: Signal): boolean {
  return a.type === 'level_shift' || a.type === 'dau_level_shift'
}

export function observationLabel(a: Signal, detectorLabel: string): string {
  return `${isLevelShift(a) ? '変化点' : detectorLabel}${a.product ? ` · ${a.product.toUpperCase()}` : ''}`
}

/** One short sentence per signal: what, how much, compared with what. */
export function signalSentence(a: Signal, kind: DayKind = 'workday'): string {
  switch (a.type) {
    case 'token_spike':
    case 'token_notable':
      return `${productName(a.product)}のトークン ${compact(a.value)}${ratioText(a.value, a.baseline, kind, a.score)}`
    case 'tokens_per_user_spike':
    case 'tokens_per_user_notable':
      return `1人あたり${productName(a.product)} ${compact(a.value)}${ratioText(a.value, a.baseline, kind, a.score)}`
    case 'dau_spike':
    case 'dau_spike_notable':
      return `${productName(a.product)}のDAU ${fmt(a.value)}人（普段 ${fmt(a.baseline ?? 0)}人${sdText(a.score)}）`
    case 'dau_drop':
    case 'dau_drop_notable':
      return `${productName(a.product)}のDAU ${fmt(a.value)}人に減少（普段 ${fmt(a.baseline ?? 0)}人${sdText(a.score)}）`
    case 'level_shift': {
      const ratio = a.baseline ? `、約${(a.value / a.baseline >= 10 ? Math.round(a.value / a.baseline) : (a.value / a.baseline).toFixed(1))}倍` : ''
      return `${productName(a.product)}のトークンがこの日から${a.span_days ?? ''}日続けて多め（1日あたり 普段 ${compact(a.baseline ?? 0)} → ${compact(a.value)}${ratio}）`
    }
    case 'dau_level_shift':
      return `${productName(a.product)}の利用者がこの日から${a.span_days ?? ''}日続けて多め（普段 ${fmt(a.baseline ?? 0)}人 → ${fmt(a.value)}人）`
    case 'dau_new_max':
      return `${productName(a.product)}の利用者 ${fmt(a.value)}人は直前28日で最多（これまでの最多 ${fmt(a.baseline ?? 0)}人、+${fmt(a.value - (a.baseline ?? 0))}人）`
    case 'holiday_usage':
      return `休日なのに平日並みの利用 ${compact(a.value)}（平日の ${Math.round((a.value / (a.baseline || 1)) * 100)}%）`
    case 'stale_data':
      return a.reason
    default:
      return `${a.metric}: ${a.reason}`
  }
}

/** Dates with at least one non-info signal: the unit the analyst reasons about. */
export function signalDates(alerts: Signal[]): Set<string> {
  return new Set(alerts.filter((a) => a.severity !== 'info').map((a) => a.date))
}

const SEVERITY_RANK: Record<Signal['severity'], number> = { high: 0, medium: 1, info: 2 }

export function strongest(list: Signal[]): Signal | undefined {
  return [...list].sort(
    (x, y) => SEVERITY_RANK[x.severity] - SEVERITY_RANK[y.severity] || y.value / (y.baseline || 1) - x.value / (x.baseline || 1),
  )[0]
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${fmt(bytes)} B`
  return `${new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 1 }).format(bytes / 1024)} KiB`
}
