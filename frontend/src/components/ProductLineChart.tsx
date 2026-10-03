import { Typography } from '@mui/material'
import ReactECharts from 'echarts-for-react'
import { useMemo, useRef } from 'react'

import { PRODUCTS, type DailyRow } from '../api/types'
import { compact, fmt } from '../lib/format'
import { colors } from '../theme'

interface Props {
  rows: DailyRow[]
  metric: 'active_users' | 'tokens'
  /** Called after the viewer drags a range on the chart (dates inclusive). */
  onRange?: (start: string, end: string) => void
  height?: number
}

const LABELS: Record<string, string> = { chat: 'Chat', codex: 'Codex', work: 'Work' }

export default function ProductLineChart({ rows, metric, onRange, height = 260 }: Props) {
  const chart = useRef<ReactECharts>(null)
  const option = useMemo(() => {
    const dates = rows.map((row) => row.date)
    const holidays = new Set(rows.filter((row) => row.day_kind === 'holiday').map((row) => row.date))
    return {
      animation: false,
      grid: { left: 64, right: 18, top: 18, bottom: 42 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: number) => fmt(value),
      },
      legend: { show: false },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: {
          formatter: (value: string) => value.slice(5),
          color: (value: string) => (holidays.has(value) ? colors.red : colors.muted),
        },
        axisTick: { show: false },
      },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => compact(value) }, splitLine: { lineStyle: { color: '#ebe7df' } } },
      // Drag selection: brush along x, no toolbox buttons.
      brush: onRange ? { xAxisIndex: 0, brushType: 'lineX', brushMode: 'single', transformable: false, brushStyle: { color: 'rgba(23,107,77,0.15)', borderColor: colors.chat } } : undefined,
      toolbox: { show: false },
      series: PRODUCTS.map((product) => ({
        name: LABELS[product],
        type: 'line',
        data: rows.map((row) => (row[metric] ? row[metric]![product] : null)),
        connectNulls: false,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 3, color: colors[product] },
        itemStyle: { color: colors[product] },
      })),
    }
  }, [rows, metric, onRange])

  if (!rows.some((row) => row[metric])) {
    return <Typography color="text.secondary" sx={{ py: 6, textAlign: 'center' }}>指定期間にデータがありません</Typography>
  }

  return (
    <ReactECharts
      ref={chart}
      option={option}
      notMerge
      style={{ height }}
      onChartReady={(instance) => {
        if (onRange) instance.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: 'lineX', brushMode: 'single' } })
      }}
      onEvents={{
        brushEnd: (params: { areas?: { coordRange: [number, number] }[] }) => {
          const area = params.areas?.[0]
          if (!area || !onRange) return
          const [from, to] = area.coordRange
          const start = Math.max(0, Math.min(rows.length - 1, Math.round(from)))
          const end = Math.max(0, Math.min(rows.length - 1, Math.round(to)))
          chart.current?.getEchartsInstance().dispatchAction({ type: 'brush', areas: [] })
          onRange(rows[Math.min(start, end)].date, rows[Math.max(start, end)].date)
        },
      }}
    />
  )
}
