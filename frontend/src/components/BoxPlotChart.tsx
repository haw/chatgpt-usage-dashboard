import { Typography } from '@mui/material'
import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

import type { DailyRow, DayKind, Signal, TriageEntry } from '../api/types'
import { compact, fmt } from '../lib/format'
import { daysBefore, metricOf, quantile } from '../lib/stats'
import { colors } from '../theme'

interface Props {
  signal: Signal
  rows: DailyRow[]
  date: string
  kind: DayKind
  /** Other triage entries, used to leave already-flagged days out of the baseline like the server does. */
  entries: TriageEntry[]
}

/** Horizontal box plot of the baseline days with the threshold and this day's value. */
export default function BoxPlotChart({ signal, rows, date, kind, entries }: Props) {
  const model = useMemo(() => {
    const sameKind: DayKind = signal.detector === 'holiday_usage' ? 'workday' : kind
    const dayRow = rows.find((r) => r.date === date)
    const dayValue = dayRow ? metricOf(signal, dayRow) : signal.value
    const since = daysBefore(date, 28)
    const flagged = new Set(
      entries.filter((e) => e.date < date).filter((e) => e.observations.some((o) => o.severity !== 'info' && o.detector === signal.detector && o.product === signal.product)).map((e) => e.date),
    )
    const baseline = rows
      .filter((r) => r.date < date && r.date >= since && r.day_kind === sameKind && !flagged.has(r.date))
      .map((r) => ({ date: r.date, value: metricOf(signal, r) }))
      .filter((p): p is { date: string; value: number } => p.value != null)
    const sorted = baseline.map((p) => p.value).sort((a, b) => a - b)
    const q1 = quantile(sorted, 0.25)
    const median = quantile(sorted, 0.5)
    const q3 = quantile(sorted, 0.75)
    const iqr = q3 - q1
    const inRange = sorted.filter((v) => v >= q1 - 1.5 * iqr && v <= q3 + 1.5 * iqr)
    const low = inRange.length ? inRange[0] : q1
    const high = inRange.length ? inRange[inRange.length - 1] : q3
    const outliers = baseline.filter((p) => p.value < low || p.value > high)
    return { sameKind, dayValue, sorted, box: [low, q1, median, q3, high], outliers, baseline }
  }, [signal, rows, date, kind, entries])

  if (model.dayValue == null) return null
  const refLabel = signal.detector === 'dau_increase' ? 'これまでの最多' : signal.detector === 'holiday_usage' ? '平日の中央値' : '中央値'
  const refValue = signal.detector === 'dau_increase' ? signal.baseline : model.box[2]
  const max = Math.max(1, model.dayValue, signal.threshold ?? 0, ...model.sorted) * 1.08
  const option = {
    animation: false,
    grid: { left: 20, right: 20, top: 26, bottom: 28 },
    tooltip: { trigger: 'item' },
    xAxis: { type: 'value', min: 0, max, axisLabel: { formatter: (v: number) => compact(v) }, splitLine: { lineStyle: { color: '#ebe7df' } } },
    yAxis: { type: 'category', data: [''], axisLine: { show: false }, axisTick: { show: false } },
    series: [
      {
        type: 'boxplot',
        data: [model.box],
        itemStyle: { color: 'rgba(52,120,164,0.18)', borderColor: colors.codex, borderWidth: 1.5 },
        boxWidth: ['40%', '40%'],
        tooltip: { formatter: () => `基準 ${model.sorted.length}日: 最小 ${compact(model.box[0])} / 25% ${compact(model.box[1])} / 中央値 ${compact(model.box[2])} / 75% ${compact(model.box[3])} / 最大 ${compact(model.box[4])}` },
        markLine: {
          symbol: 'none',
          silent: true,
          data: [
            ...(signal.threshold != null ? [{ xAxis: signal.threshold, lineStyle: { type: 'dotted', color: '#b8651b', width: 2 }, label: { formatter: `判定ライン ${compact(signal.threshold)}`, position: 'insideEndTop', color: '#b8651b' } }] : []),
            ...(refValue != null ? [{ xAxis: refValue, lineStyle: { type: 'dashed', color: '#68736c', width: 1.5 }, label: { formatter: `${refLabel} ${compact(refValue)}`, position: 'insideEndBottom', color: '#68736c' } }] : []),
          ],
        },
      },
      { type: 'scatter', data: model.outliers.map((p) => [p.value, 0]), symbolSize: 7, itemStyle: { color: colors.codex }, tooltip: { formatter: (item: { dataIndex: number }) => `${model.outliers[item.dataIndex].date} ${fmt(Math.round(model.outliers[item.dataIndex].value))}` } },
      { type: 'scatter', data: [[model.dayValue, 0]], symbol: 'diamond', symbolSize: 20, itemStyle: { color: colors.red, borderColor: '#fff', borderWidth: 1.5 }, label: { show: true, position: 'bottom', formatter: `この日 ${compact(model.dayValue)}`, color: colors.red, fontWeight: 'bold' }, tooltip: { formatter: () => `${date} ${fmt(Math.round(model.dayValue!))}` } },
    ],
  }
  return (
    <>
      <ReactECharts option={option} notMerge style={{ height: 150 }} />
      <Typography variant="caption" color="text.secondary">
        分布 — 箱ひげ: 基準にした{model.sameKind === 'holiday' ? '休日' : '平日'} {model.sorted.length}日（箱＝中央50%、線＝中央値、ひげ＝通常の範囲）· 点線: 判定ライン · ◆ この日
      </Typography>
    </>
  )
}
