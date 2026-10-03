import { Stack, Typography } from '@mui/material'
import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'

import type { AnalysisPoint } from '../api/types'
import { compact, fmt } from '../lib/format'
import { colors } from '../theme'

/** Actual total tokens with the median and the threshold line; anomalies as red points. */
export default function AnomalyChart({ points, narrowed, height = 280 }: { points: AnalysisPoint[]; narrowed: boolean; height?: number }) {
  const option = useMemo(() => {
    const dates = points.map((p) => p.date)
    const holidays = new Set(points.filter((p) => p.kind === 'holiday').map((p) => p.date))
    return {
      animation: false,
      grid: { left: 64, right: 18, top: 18, bottom: 42 },
      tooltip: {
        trigger: 'axis',
        formatter: (items: { dataIndex: number }[]) => {
          const p = points[items[0]?.dataIndex ?? 0]
          if (!p) return ''
          const lines = [`${p.date}${p.kind === 'holiday' ? '（休日）' : ''} 実測: ${fmt(p.value)}`]
          if (p.baseline == null) lines.push('判定保留: 同じ区分の基準が不足')
          else lines.push(`中央値: ${fmt(p.baseline)} / 判定ライン: ${fmt(p.threshold ?? 0)}`)
          if (p.is_anomaly) lines.push('検出点')
          else if (p.is_notable) lines.push('参考点（判定ライン未満の上振れ）')
          return lines.join('<br/>')
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { formatter: (value: string) => value.slice(5), color: (value: string) => (holidays.has(value) ? colors.red : colors.muted) },
        axisTick: { show: false },
      },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => compact(value) }, splitLine: { lineStyle: { color: '#ebe7df' } } },
      series: [
        { name: '判定ライン', type: 'line', data: points.map((p) => p.threshold), symbol: 'none', lineStyle: { type: 'dotted', width: 2, color: '#b8651b' }, connectNulls: false },
        { name: '中央値', type: 'line', data: points.map((p) => p.baseline), symbol: 'none', lineStyle: { type: 'dashed', width: 2, color: '#68736c' }, connectNulls: false },
        { name: '実測値', type: 'line', data: points.map((p) => p.value), symbol: 'circle', symbolSize: 6, lineStyle: { width: 3, color: colors.chat }, itemStyle: { color: colors.chat } },
        { name: '参考点', type: 'scatter', data: points.map((p, i) => (p.is_notable ? [i, p.value] : null)).filter(Boolean), symbolSize: 10, itemStyle: { color: '#e0a24a', borderColor: '#fff', borderWidth: 1 }, tooltip: { show: false } },
        { name: '検出点', type: 'scatter', data: points.map((p, i) => (p.is_anomaly ? [i, p.value] : null)).filter(Boolean), symbolSize: 14, itemStyle: { color: colors.red, borderColor: '#fff', borderWidth: 2 }, tooltip: { show: false } },
      ],
    }
  }, [points])

  if (!points.length) {
    return <Typography color="text.secondary" sx={{ py: 6, textAlign: 'center' }}>指定期間にデータがありません</Typography>
  }
  return (
    <>
      <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap', fontSize: '0.72rem', color: 'text.secondary', mb: 0.5 }}>
        <span>── 実測値</span><span>- - 中央値</span><span>··· 判定ライン</span><span style={{ color: colors.red }}>● 検出点</span><span style={{ color: '#e0a24a' }}>● 参考点</span>
      </Stack>
      <ReactECharts option={option} notMerge style={{ height }} />
      <Typography variant="caption" color="text.secondary">
        {narrowed ? '選択期間内の同じ区分の日' : '同じ区分の直前28日'}から計算
      </Typography>
    </>
  )
}
