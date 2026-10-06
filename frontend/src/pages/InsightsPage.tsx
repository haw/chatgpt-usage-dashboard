import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, Chip, Paper, Stack, Typography } from '@mui/material'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'

import { getJson, postJson } from '../api/client'
import type { TriageEntry, TriageResponse } from '../api/types'
import ContextDialog from '../components/ContextDialog'
import LevelShiftSwitch from '../components/LevelShiftSwitch'
import TriageEntryCard from '../components/TriageEntryCard'
import { dateLabel, fmt } from '../lib/format'
import { useViewer } from '../state/viewer'

export default function InsightsPage() {
  const viewer = useViewer()
  const navigate = useNavigate()
  const { date } = useParams()
  const queryClient = useQueryClient()
  const triage = useQuery({
    queryKey: ['triage', viewer.params.holidays, viewer.params.workdays, viewer.params.level_shifts],
    queryFn: () => getJson<TriageResponse>('/api/triage', { holidays: viewer.params.holidays, workdays: viewer.params.workdays, level_shifts: viewer.params.level_shifts }),
    placeholderData: keepPreviousData,
  })
  const mark = useMutation({
    mutationFn: (input: { date: string; kind: 'checked' | 'cleared' }) => postJson('/api/dispositions', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['triage'] }),
  })
  const reset = useMutation({
    mutationFn: () => postJson('/api/dispositions/reset', {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['triage'] }),
  })
  const data = triage.data
  const status = data?.status
  const entries = new Map<string, TriageEntry>([...(data?.today ?? []), ...(data?.week ?? []), ...(data?.reference ?? [])].map((e) => [e.date, e]))
  const selected = date ? entries.get(date) : undefined
  // The API's reference tier holds both checked days and days with only below-threshold observations.
  const checked = (data?.reference ?? []).filter((e) => e.disposition)
  const weak = (data?.reference ?? []).filter((e) => !e.disposition)

  const list = (items: TriageEntry[], empty: string) =>
    items.length ? (
      <Stack spacing={1.25}>
        {items.map((entry) => (
          <TriageEntryCard key={entry.date} entry={entry} busy={mark.isPending} onMark={(kind) => mark.mutate({ date: entry.date, kind })} onInspect={() => navigate(`/insights/${entry.date}`)} />
        ))}
      </Stack>
    ) : (
      <Typography color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>{empty}</Typography>
    )

  return (
    <Stack spacing={2}>
      <Paper sx={{ px: 2.5, py: 1.75 }}>
        <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          {status?.latest_date ? (
            <Typography variant="body2">
              最終データ日 <strong>{dateLabel(status.latest_date)}</strong>（{status.age_days}日前）· 保存 {fmt(status.stored_days)}日分 · 基準: {status.baseline}
              {status.pending_days ? ` · 判定保留 ${status.pending_days}日` : ''}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">{triage.isLoading ? '読み込み中…' : 'データがありません。「推移」からJSONを取り込んでください。'}</Typography>
          )}
          <LevelShiftSwitch />
        </Stack>
        {status?.stale && <Alert severity="error" sx={{ mt: 1 }}>取込が止まっています: {status.stale_reason}</Alert>}
        {triage.error && <Alert severity="error" sx={{ mt: 1 }}>読み込みに失敗しました: {(triage.error as Error).message}</Alert>}
        {mark.error && <Alert severity="error" sx={{ mt: 1 }}>記録に失敗しました: {(mark.error as Error).message}</Alert>}
        {data?.detector_errors?.length ? <Alert severity="error" sx={{ mt: 1 }}>判定の設定に問題があります: {data.detector_errors.join(' / ')}</Alert> : null}
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <div>
            <Typography variant="overline" color="warning.main">PRIORITY</Typography>
            <Typography variant="h2">優先して確認</Typography>
          </div>
          {data?.today.length ? <Chip label={`${data.today.length}日`} size="small" /> : null}
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
          同じ区分の直前28日と比べて普段と違う日を、反応した観点の数・その日に始まった変化か・初めてのパターンかで並べます。感度の設定には影響されません。表示は不正の断定ではなく調査のきっかけです。
        </Typography>
        {list(data?.today ?? [], status?.latest_date ? '優先して確認する日はありません' : '')}
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <div>
            <Typography variant="overline">NEXT</Typography>
            <Typography variant="h2">次に確認</Typography>
          </div>
          {data?.week.length ? <Chip label={`${data.week.length}日`} size="small" /> : null}
        </Stack>
        {list(data?.week ?? [], '次に確認する日はありません')}
      </Paper>
      <Accordion disableGutters sx={{ '&:before': { display: 'none' } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flex: 1 }}>
            <Typography variant="overline">CHECKED</Typography>
            <Typography variant="h2">確認済み</Typography>
            {checked.length ? <Chip label={`${checked.length}日`} size="small" /> : null}
            {status?.checked_days ? (
              <Button size="small" variant="outlined" disabled={reset.isPending} onClick={(event) => { event.stopPropagation(); reset.mutate() }} sx={{ ml: 'auto' }}>
                確認済み {status.checked_days}日をすべて解除
              </Button>
            ) : null}
          </Stack>
        </AccordionSummary>
        <AccordionDetails>{list(checked, '確認済みの日はありません')}</AccordionDetails>
      </Accordion>
      <Accordion disableGutters sx={{ '&:before': { display: 'none' } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flex: 1 }}>
            <Typography variant="overline">REFERENCE</Typography>
            <Typography variant="h2">参考</Typography>
            {weak.length ? <Chip label={`${weak.length}日`} size="small" /> : null}
            <Typography variant="caption" color="text.secondary">判定ラインは超えていないが、普段より大きく上振れした兆候だけの日</Typography>
          </Stack>
        </AccordionSummary>
        <AccordionDetails>{list(weak, '参考の日はありません')}</AccordionDetails>
      </Accordion>
      <ContextDialog entry={selected} entries={[...entries.values()]} open={Boolean(date)} onClose={() => navigate('/insights')} />
    </Stack>
  )
}
