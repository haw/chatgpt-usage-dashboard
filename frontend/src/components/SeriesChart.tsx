import { Typography } from '@mui/material'
import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

import type { DailyRow, DayKind, Signal } from '../api/types'
import { compact, fmt, isLevelShift } from '../lib/format'
import { metricOf } from '../lib/stats'
import { colors } from '../theme'

interface Props {
  signal: Signal
  rows: DailyRow[]
  date: string
  kind: DayKind
}

/** The same metric over time: same-kind days joined by a line, other days faded, this day in red. */
export default function SeriesChart({ signal, rows, date, kind }: Props) {
  const sameKind: DayKind = signal.detector === 'holiday_usage' ? 'workday' : kind
  const points = useMemo(
    () => rows.map((r) => ({ date: r.date, value: metricOf(signal, r), kind: r.day_kind })).filter((p): p is { date: string; value: number; kind: DayKind } => p.value != null),
    [rows, signal],
  )
  if (!points.length) return null
  const shift = isLevelShift(signal)
  const refLabel = shift ? 'それまでの水準' : signal.detector === 'dau_increase' ? 'これまでの最多' : signal.detector === 'holiday_usage' ? '平日の中央値' : '中央値'
  // the same-kind days that made up the shift: from this day, span_days of them
  const run = shift ? points.filter((p) => p.kind === sameKind && p.date >= date).slice(0, signal.span_days ?? 1) : []
  const option = {
    animation: false,
    grid: { left: 58, right: 14, top: 14, bottom: 28 },
    tooltip: { trigger: 'axis', formatter: (items: { dataIndex: number }[]) => { const p = points[items[0]?.dataIndex]; return p ? `${p.date}${p.kind === 'holiday' ? '（休日）' : '（平日）'} ${fmt(Math.round(p.value))}` : '' } },
    xAxis: { type: 'category', data: points.map((p) => p.date), axisLabel: { formatter: (v: string) => v.slice(5), color: (v: string) => (v === date ? colors.red : colors.muted) }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => compact(v) }, splitLine: { lineStyle: { color: '#ebe7df' } } },
    series: [
      {
        name: '基準の系列', type: 'line', connectNulls: true, symbol: 'none', lineStyle: { width: 2, color: colors.codex },
        data: points.map((p) => (p.kind === sameKind || p.date === date ? p.value : null)),
        markLine: {
          symbol: 'none', silent: true,
          data: [
            ...(signal.threshold != null ? [{ yAxis: signal.threshold, lineStyle: { type: 'dotted', color: '#b8651b', width: 2 }, label: { formatter: `判定ライン ${compact(signal.threshold)}`, position: 'insideEndTop', color: '#b8651b' } }] : []),
            ...(signal.baseline != null ? [{ yAxis: signal.baseline, lineStyle: { type: 'dashed', color: '#68736c', width: 1.5 }, label: { formatter: `${refLabel} ${compact(signal.baseline)}`, position: 'insideEndBottom', color: '#68736c' } }] : []),
            ...(shift ? [{ yAxis: signal.value, lineStyle: { type: 'dotted', color: '#b8651b', width: 2 }, label: { formatter: `新しい水準 ${compact(signal.value)}`, position: 'insideEndTop', color: '#b8651b' } }] : []),
            { xAxis: date, lineStyle: { type: 'dashed', color: colors.red, width: 1, opacity: 0.6 }, label: { show: false } },
          ],
        },
        ...(run.length > 1 ? { markArea: { silent: true, itemStyle: { color: colors.red, opacity: 0.07 }, data: [[{ xAxis: run[0].date }, { xAxis: run[run.length - 1].date }]] } } : {}),
      },
      { name: '同じ区分', type: 'scatter', data: points.map((p, i) => (p.kind === sameKind && p.date !== date ? [i, p.value] : null)).filter(Boolean), symbolSize: 7, itemStyle: { color: colors.codex }, tooltip: { show: false } },
      { name: '別の区分', type: 'scatter', data: points.map((p, i) => (p.kind !== sameKind && p.date !== date ? [i, p.value] : null)).filter(Boolean), symbolSize: 5, itemStyle: { color: '#c8cdc9', opacity: 0.7 }, tooltip: { show: false } },
      { name: 'この日', type: 'scatter', data: points.map((p, i) => (p.date === date ? [i, p.value] : null)).filter(Boolean), symbolSize: 13, itemStyle: { color: colors.red, borderColor: '#fff', borderWidth: 2 }, tooltip: { show: false } },
    ],
  }
  return (
    <>
      <ReactECharts option={option} notMerge style={{ height: 190 }} />
      <Typography variant="caption" color="text.secondary">
        推移 — 実線: {sameKind === 'holiday' ? '休日' : '平日'}の流れ（基準に使う系列）· 薄い点: {sameKind === 'holiday' ? '平日' : '休日'}（基準に含まない）· 赤: この日{run.length > 1 ? '・薄い赤の帯: 多めが続いた期間' : ''}
      </Typography>
    </>
  )
}
