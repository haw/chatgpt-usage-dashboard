import { Box, Button, Chip, Paper, Stack, Typography } from '@mui/material'

import type { TriageEntry } from '../api/types'
import { compact, dateLabel, fmt, kindLabel, signalSentence } from '../lib/format'
import { colors } from '../theme'

const TIER = {
  today: { label: '優先', bg: colors.red, color: '#fff', border: colors.red },
  week: { label: '次に', bg: '#f6dcd7', color: colors.red, border: '#d9a9a2' },
  reference: { label: '確認済み', bg: '#e6ebe8', color: colors.muted, border: colors.line },
} as const

interface Props {
  entry: TriageEntry
  busy: boolean
  onMark: (kind: 'checked' | 'cleared') => void
  onInspect: () => void
}

export default function TriageEntryCard({ entry, busy, onMark, onInspect }: Props) {
  const f = entry.facts
  const tier = TIER[entry.tier]
  const facts = [kindLabel(f.kind, f.kind_source), f.max_dau != null ? `DAU ${fmt(f.max_dau)}` : null, f.total_tokens != null ? `${compact(f.total_tokens)} tokens` : null].filter(Boolean)
  const checked = Boolean(entry.disposition)
  const strong = entry.observations.filter((o) => o.severity !== 'info')
  const info = entry.observations.filter((o) => o.severity === 'info')
  const line = (o: TriageEntry['observations'][number], index: number) => (
    <Box component="li" key={`${o.detector}-${o.product ?? 'all'}-${index}`} sx={{ fontSize: '0.88rem', fontWeight: o.severity === 'high' ? 700 : 400, color: o.severity === 'info' ? 'text.secondary' : 'inherit', display: 'flex', gap: 1.25, flexWrap: 'wrap', alignItems: 'baseline' }}>
      <span>{signalSentence(o, f.kind)}</span>
      {o.threshold != null && o.detector !== 'dau_increase' && <Typography variant="caption" color="text.secondary">判定ライン {compact(o.threshold)}</Typography>}
      {o.streak > 1 && <Typography variant="caption" color="text.secondary">{o.streak}日連続</Typography>}
    </Box>
  )
  return (
    <Paper sx={{ p: 2, borderLeft: `5px solid ${tier.border}`, opacity: entry.tier === 'reference' ? 0.85 : 1 }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Chip label={tier.label} size="small" sx={{ bgcolor: tier.bg, color: tier.color, fontWeight: 800, height: 22 }} />
        <Typography sx={{ fontSize: '1.05rem', fontWeight: 800 }}>{dateLabel(entry.date)}</Typography>
        <Typography variant="body2" color="text.secondary">{facts.join(' · ')}</Typography>
      </Stack>
      <Box component="ul" sx={{ listStyle: 'none', m: 0, mt: 1.25, p: 0, display: 'grid', gap: 0.75 }}>{strong.map(line)}</Box>
      {info.length > 0 && (
        <Box component="details" sx={{ mt: 1, fontSize: '0.8rem', color: 'text.secondary', '& summary': { cursor: 'pointer' } }}>
          <summary>参考 {info.length}件</summary>
          <Box component="ul" sx={{ listStyle: 'none', m: 0, mt: 0.5, p: 0, display: 'grid', gap: 0.5 }}>{info.map(line)}</Box>
        </Box>
      )}
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 1.5, pt: 1.25, borderTop: '1px dashed', borderColor: 'divider', flexWrap: 'wrap' }}>
        {checked && (
          <Typography variant="body2" color="primary.main" sx={{ fontWeight: 700 }}>
            確認済み <Typography component="span" variant="caption" color="text.secondary">{new Date(entry.disposition!.recorded_at).toLocaleDateString('ja-JP')}</Typography>
          </Typography>
        )}
        <Button size="small" variant="outlined" disabled={busy} onClick={() => onMark(checked ? 'cleared' : 'checked')}>
          {checked ? '未確認に戻す' : '確認済みにする'}
        </Button>
        <Button size="small" variant="text" onClick={onInspect} sx={{ ml: 'auto' }}>
          グラフで見る
        </Button>
      </Stack>
    </Paper>
  )
}
