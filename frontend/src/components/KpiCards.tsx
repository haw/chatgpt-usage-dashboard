import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import { Box, ButtonBase, Grid, Paper, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'

import type { DashboardResponse, TriageResponse } from '../api/types'
import { fmt, formatOptional } from '../lib/format'

function Card({ label, value, note, color }: { label: string; value: string; note: string; color?: string }) {
  return (
    <Paper sx={{ p: 2.2, height: '100%', display: 'flex', flexDirection: 'column', minHeight: 128 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography className="mono" sx={{ fontSize: '2.1rem', fontWeight: 700, my: 1, color }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 'auto' }}>{note}</Typography>
    </Paper>
  )
}

export default function KpiCards({ dashboard, triage }: { dashboard?: DashboardResponse; triage?: TriageResponse }) {
  const navigate = useNavigate()
  const kpis = dashboard?.kpis
  const today = triage?.today.length ?? 0
  const week = triage?.week.length ?? 0
  const hasData = Boolean(triage?.status.latest_date)
  return (
    <Grid container spacing={1.75}>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card label="最新日の製品別最大DAU" value={formatOptional(kpis?.latest_max_product_dau)} note="製品間の重複があるため合算しません" />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card label="期間総トークン" value={formatOptional(kpis?.total_tokens)} note="Chat + Codex + Work" />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <Card label="1日平均トークン" value={formatOptional(kpis?.daily_average_tokens)} note="トークンデータがある日の日平均" />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}>
        <ButtonBase onClick={() => navigate('/insights')} sx={{ width: '100%', height: '100%', textAlign: 'left', borderRadius: 3 }} aria-label="インサイトへ移動">
          <Paper sx={{ p: 2.2, width: '100%', minHeight: 128, display: 'flex', flexDirection: 'column', position: 'relative', borderColor: '#ecd6c4', '&:hover': { boxShadow: '0 14px 34px #1c2c2322' } }}>
            <Typography variant="body2" color="text.secondary">インサイト（優先）</Typography>
            <Typography className="mono" sx={{ fontSize: '2.1rem', fontWeight: 700, my: 1, color: hasData && today === 0 ? 'primary.main' : 'warning.main' }}>
              {hasData ? fmt(today) : '—'}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 'auto' }}>
              {hasData ? `${week ? `次に ${week}日 · ` : ''}${triage?.status.stale ? '取込が止まっています · ' : ''}クリックで一覧へ` : 'データ取込後に判定'}
            </Typography>
            <Box sx={{ position: 'absolute', right: 14, bottom: 14, color: 'text.secondary' }}><ArrowForwardIcon fontSize="small" /></Box>
          </Paper>
        </ButtonBase>
      </Grid>
    </Grid>
  )
}
