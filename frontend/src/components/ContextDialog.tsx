import { Alert, Dialog, DialogContent, DialogTitle, IconButton, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { useQuery } from '@tanstack/react-query'

import { getJson } from '../api/client'
import type { ContextResponse, DetectorInfo, TriageEntry } from '../api/types'
import { dateLabel, isLevelShift, observationLabel, signalSentence } from '../lib/format'
import { useViewer, type ContextMode } from '../state/viewer'
import AiReading from './AiReading'
import BoxPlotChart from './BoxPlotChart'
import SeriesChart from './SeriesChart'

interface Props {
  entry?: TriageEntry
  /** Every triage entry, so charts can leave already-flagged days out of the baseline like the server does. */
  entries: TriageEntry[]
  open: boolean
  onClose: () => void
}

/** "How it crossed the line": one figure (or two) per observation of the selected day. */
export default function ContextDialog({ entry, entries, open, onClose }: Props) {
  const viewer = useViewer()
  const detectors = useQuery({ queryKey: ['detectors'], queryFn: () => getJson<{ detectors: DetectorInfo[] }>('/api/detectors'), staleTime: Infinity })
  const labelOf = (id: string) => detectors.data?.detectors.find((d) => d.id === id)?.label ?? id
  const context = useQuery({
    queryKey: ['context', entry?.date, viewer.params.holidays, viewer.params.workdays],
    queryFn: () => getJson<ContextResponse>('/api/context', { date: entry!.date, holidays: viewer.params.holidays, workdays: viewer.params.workdays }),
    enabled: open && Boolean(entry),
  })
  const observations = entry?.observations.filter((o) => o.severity !== 'info') ?? []
  const shown = observations.length ? observations : (entry?.observations ?? [])
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth scroll="body">
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <div>
          <Typography variant="overline" color="warning.main">HOW IT CROSSED THE LINE</Typography>
          <Typography variant="h2">{entry ? `${dateLabel(entry.date)} の判定` : '—'}</Typography>
        </div>
        <IconButton onClick={onClose} aria-label="閉じる" sx={{ ml: 'auto' }}><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent>
        {!entry && open && <Alert severity="info">この日はインサイトの一覧にありません。</Alert>}
        {entry && (
          <Stack spacing={2}>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <Typography variant="body2" color="text.secondary">
                観点ごとに、<strong>分布</strong>（基準にした日々の箱ひげ図の中でこの日がどこか）と<strong>推移</strong>（同じ区分の日の流れの中でこの日がどうか）を見られます。
              </Typography>
              <ToggleButtonGroup size="small" exclusive value={viewer.contextMode} onChange={(_, mode: ContextMode | null) => mode && viewer.setContextMode(mode)} aria-label="グラフの種類">
                <ToggleButton value="box">分布</ToggleButton>
                <ToggleButton value="series">推移</ToggleButton>
                <ToggleButton value="both">両方</ToggleButton>
              </ToggleButtonGroup>
            </Stack>
            <AiReading entry={entry} />
            {context.error && <Alert severity="error">読み込みに失敗しました: {(context.error as Error).message}</Alert>}
            {context.data &&
              shown.map((o, index) => (
                <Stack key={`${o.detector}-${o.product ?? 'all'}-${index}`} spacing={0.5} sx={{ border: 1, borderColor: 'divider', borderRadius: 2, p: 1.5 }}>
                  <Typography variant="subtitle2">{observationLabel(o, labelOf(o.detector))}</Typography>
                  <Typography variant="body2" color="text.secondary">{signalSentence(o, entry.facts.kind)}</Typography>
                  {/* a level shift is about a run of days: only the series over time shows it */}
                  {viewer.contextMode !== 'series' && !isLevelShift(o) && <BoxPlotChart signal={o} rows={context.data.rows} date={entry.date} kind={entry.facts.kind} entries={entries} />}
                  {(viewer.contextMode !== 'box' || isLevelShift(o)) && <SeriesChart signal={o} rows={context.data.rows} date={entry.date} kind={entry.facts.kind} />}
                </Stack>
              ))}
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  )
}
