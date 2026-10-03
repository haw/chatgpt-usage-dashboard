import { Box, Chip, List, ListItem, Typography } from '@mui/material'
import { useEffect, useRef } from 'react'

import type { DailyRow, Signal } from '../api/types'
import { compact, dateLabel, signalDates, signalSentence, strongest } from '../lib/format'
import { sensitivityLabel, useViewer } from '../state/viewer'
import { colors } from '../theme'

interface Props {
  alerts: Signal[]
  daily: DailyRow[]
  pendingDays: number
}

/**
 * Every day detected at the current sensitivity, with the strongest observation per day.
 * Right after a sensitivity change, days that newly crossed the line are highlighted.
 */
export default function DetectedDays({ alerts, daily, pendingDays }: Props) {
  const { sensitivity } = useViewer()
  const previous = useRef<{ label: string; dates: Set<string> } | null>(null)
  const shown = useRef<{ label: string; alerts: Signal[] } | null>(null)

  const current = signalDates(alerts)
  const label = sensitivityLabel(sensitivity)
  // Remember what was shown under the previous sensitivity to explain the change.
  useEffect(() => {
    if (shown.current && shown.current.label !== label) previous.current = { label: shown.current.label, dates: signalDates(shown.current.alerts) }
    shown.current = { label, alerts }
  }, [alerts, label])
  const changed = previous.current && previous.current.label !== label ? previous.current : null
  const added = new Set(changed ? [...current].filter((d) => !changed.dates.has(d)) : [])
  const dropped = changed ? [...changed.dates].filter((d) => !current.has(d)).length : 0
  const kindOf = (date: string) => daily.find((row) => row.date === date)?.day_kind ?? 'workday'

  if (!current.size && !changed) {
    return pendingDays ? <Typography variant="caption" color="text.secondary">判定保留 {pendingDays}日（同じ区分の基準データが不足）</Typography> : null
  }
  const title = changed
    ? `感度を ${changed.label} → ${label} に変更: 検出 ${current.size}日${added.size ? `、新たに ${added.size}日` : dropped ? `（${dropped}日減）` : '（変化なし）'}`
    : `現在の判定で検出された日: ${current.size}日`
  return (
    <Box sx={{ mt: 1.5, p: 1.5, borderRadius: 2, bgcolor: '#fbfaf7', border: 1, borderColor: 'divider', fontSize: '0.8rem' }}>
      <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>{title}</Typography>
      <List dense disablePadding>
        {[...current].sort().reverse().map((date) => {
          const strong = alerts.filter((a) => a.date === date && a.severity !== 'info')
          const top = strongest(strong)!
          const isNew = added.has(date)
          return (
            <ListItem key={date} disableGutters sx={{ py: 0.3, px: 0.8, borderRadius: 1, borderLeft: isNew ? `3px solid ${colors.red}` : '3px solid transparent', bgcolor: isNew ? '#fff1ec' : 'transparent', fontWeight: isNew ? 700 : 400, gap: 1, flexWrap: 'wrap' }}>
              <b>{dateLabel(date)}</b>
              <span>{signalSentence(top, kindOf(date))}</span>
              {top.threshold != null && <Typography variant="caption" color="text.secondary">判定ライン {compact(top.threshold)}</Typography>}
              {strong.length > 1 && <Typography variant="caption" color="text.secondary">ほか{strong.length - 1}件</Typography>}
              {isNew && <Chip label="新たに検出" size="small" color="error" sx={{ height: 18, fontSize: '0.65rem' }} />}
            </ListItem>
          )
        })}
      </List>
      {pendingDays > 0 && <Typography variant="caption" color="text.secondary">判定保留 {pendingDays}日（同じ区分の基準データが不足）</Typography>}
    </Box>
  )
}
