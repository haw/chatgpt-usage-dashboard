import { Alert, Box, Grid, Paper, Stack, Typography } from '@mui/material'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { getJson } from '../api/client'
import type { DashboardResponse, TriageResponse } from '../api/types'
import AnomalyChart from '../components/AnomalyChart'
import DailyTable from '../components/DailyTable'
import DetectedDays from '../components/DetectedDays'
import KpiCards from '../components/KpiCards'
import ProductLineChart from '../components/ProductLineChart'
import SensitivityControl from '../components/SensitivityControl'
import UploadCard from '../components/UploadCard'
import { useViewer } from '../state/viewer'

export interface PeriodSelection {
  start?: string
  end?: string
}

export default function TrendsPage() {
  const viewer = useViewer()
  const [period, setPeriod] = useState<PeriodSelection>({})
  const dashboard = useQuery({
    queryKey: ['dashboard', period, viewer.params],
    queryFn: () => getJson<DashboardResponse>('/api/dashboard', { start_date: period.start, end_date: period.end, ...viewer.params }),
    placeholderData: keepPreviousData, // keep charts and the table on screen while a new sensitivity/period loads
  })
  const triage = useQuery({
    queryKey: ['triage', viewer.params.holidays, viewer.params.workdays],
    queryFn: () => getJson<TriageResponse>('/api/triage', { holidays: viewer.params.holidays, workdays: viewer.params.workdays }),
    placeholderData: keepPreviousData,
  })
  const data = dashboard.data

  return (
    <Stack spacing={2}>
      <UploadCard />
      {dashboard.error && <Alert severity="error">読み込みに失敗しました: {(dashboard.error as Error).message}</Alert>}
      <KpiCards dashboard={data} triage={triage.data} />
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1, mb: 1 }}>
          <div>
            <Typography variant="overline">DAILY ACTIVE USERS</Typography>
            <Typography variant="h2">製品別アクティブユーザー</Typography>
          </div>
          <Typography variant="body2" color="text.secondary">
            {data?.selected_period.start_date ? `${data.selected_period.start_date} – ${data.selected_period.end_date}` : 'データなし'}
            {period.start || period.end ? (
              <Box component="button" onClick={() => setPeriod({})} sx={{ ml: 1, cursor: 'pointer', border: 1, borderColor: 'divider', borderRadius: 99, px: 1.2, py: 0.4, bgcolor: 'background.paper', font: 'inherit' }}>
                期間をリセット
              </Box>
            ) : null}
          </Typography>
        </Stack>
        <ProductLineChart rows={data?.daily ?? []} metric="active_users" onRange={(start, end) => setPeriod({ start, end })} />
        <Typography variant="caption" color="text.secondary">グラフ上を横にドラッグして分析期間を選択</Typography>
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">TOKENS</Typography>
        <Typography variant="h2" sx={{ mb: 1 }}>製品別トークン消費量</Typography>
        <ProductLineChart rows={data?.daily ?? []} metric="tokens" onRange={(start, end) => setPeriod({ start, end })} />
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Grid container spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Grid>
            <Typography variant="overline" color="warning.main">ANOMALY ANALYSIS</Typography>
            <Typography variant="h2">総トークン異常分析</Typography>
          </Grid>
          <Grid>
            <SensitivityControl />
          </Grid>
        </Grid>
        <AnomalyChart points={data?.analysis ?? []} narrowed={Boolean(period.start || period.end)} />
        <DetectedDays alerts={data?.alerts ?? []} daily={data?.daily ?? []} pendingDays={data?.pending_days ?? 0} />
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">DATA</Typography>
        <Typography variant="h2" sx={{ mb: 1 }}>日次データ</Typography>
        <DailyTable rows={data?.daily ?? []} alerts={data?.alerts ?? []} />
      </Paper>
    </Stack>
  )
}
