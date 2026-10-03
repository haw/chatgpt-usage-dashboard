import UploadFileIcon from '@mui/icons-material/UploadFile'
import { Alert, Button, FormControl, Grid, InputLabel, MenuItem, Paper, Select, Stack, TextField, Typography } from '@mui/material'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { getJson, postForm } from '../api/client'
import type { IndividualResponse } from '../api/types'
import AnomalyChart from '../components/AnomalyChart'
import IndividualTables from '../components/IndividualTables'
import ProductLineChart from '../components/ProductLineChart'
import { fmt } from '../lib/format'
import { quotaEstimate } from '../lib/quota'
import { useViewer } from '../state/viewer'

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <Paper sx={{ p: 2.2, minHeight: 120, display: 'flex', flexDirection: 'column' }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography className="mono" sx={{ fontSize: '1.9rem', fontWeight: 700, my: 1 }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mt: 'auto' }}>{note}</Typography>
    </Paper>
  )
}

export default function IndividualPage() {
  const viewer = useViewer()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [userId, setUserId] = useState<string | undefined>()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; severity: 'success' | 'error' | 'info' } | null>(null)
  const individual = useQuery({
    queryKey: ['individual', userId, viewer.params],
    queryFn: () => getJson<IndividualResponse>('/api/individual', { user_id: userId, ...viewer.params }),
    placeholderData: keepPreviousData,
  })
  const data = individual.data
  const rows = data?.daily ?? []
  const estimate = quotaEstimate(rows, viewer.limits)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setMessage({ text: 'JSONの形式を検証しています。', severity: 'info' })
    try {
      const result = await postForm<IndividualResponse>('/api/individual/import', form, viewer.params)
      setUserId(result.selected_user?.user_id)
      await queryClient.invalidateQueries({ queryKey: ['individual'] })
      await queryClient.invalidateQueries({ queryKey: ['individual-imports'] })
      setMessage({ text: `${result.selected_user?.user_label} の${result.state.imported_days}日分を取り込みました。`, severity: 'success' })
      event.currentTarget?.reset?.()
    } catch (error) {
      setMessage({ text: (error as Error).message, severity: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">INDIVIDUAL IMPORT</Typography>
        <Typography variant="h2">個人別トークンJSONを取り込む</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>管理画面で対象ユーザーを絞り込んだトークンJSONを選択してください。</Typography>
        <Stack component="form" onSubmit={submit} direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ alignItems: { md: 'center' } }}>
          <TextField name="user_label" label="ユーザー名またはメールアドレス" required size="small" slotProps={{ htmlInput: { maxLength: 200 } }} placeholder="user@example.com" sx={{ minWidth: 280 }} />
          <Button component="label" variant="outlined" size="medium">
            トークンJSONを選択
            <input name="tokens_file" type="file" accept=".json,application/json" required hidden />
          </Button>
          <Button type="submit" variant="contained" startIcon={<UploadFileIcon />} disabled={busy}>{busy ? '取込中…' : 'アップロードして分析'}</Button>
        </Stack>
        {message && <Alert severity={message.severity} sx={{ mt: 2 }}>{message.text}</Alert>}
        {individual.error && <Alert severity="error" sx={{ mt: 2 }}>読み込みに失敗しました: {(individual.error as Error).message}</Alert>}
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <FormControl size="small" sx={{ minWidth: 320 }} disabled={!data?.users.length}>
          <InputLabel id="individual-user">確認するユーザー</InputLabel>
          <Select labelId="individual-user" label="確認するユーザー" value={data?.selected_user?.user_id ?? ''} onChange={(event) => setUserId(event.target.value)}>
            {(data?.users ?? []).map((user) => (
              <MenuItem key={user.user_id} value={user.user_id}>{user.user_label}（{fmt(user.total_tokens)} tokens）</MenuItem>
            ))}
            {!data?.users.length && <MenuItem value="">データがありません</MenuItem>}
          </Select>
        </FormControl>
      </Paper>
      <Grid container spacing={1.75}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}><Kpi label="期間総トークン" value={fmt(data?.kpis.total_tokens ?? 0)} note="Chat + Codex + Work" /></Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}><Kpi label="1日平均トークン" value={fmt(data?.kpis.daily_average_tokens ?? 0)} note="保存期間内の日平均" /></Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}><Kpi label="最新日のトークン" value={fmt(data?.kpis.latest_tokens ?? 0)} note="選択ユーザーの最新値" /></Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}><Kpi label="要確認" value={fmt(data?.kpis.alerts ?? 0)} note="トークン急増の検出数" /></Grid>
      </Grid>
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <div>
            <Typography variant="overline" color="warning.main">LIMIT PRESSURE</Typography>
            <Typography variant="h2">利用枠への到達回数目安</Typography>
          </div>
          <Button size="small" variant="outlined" onClick={() => navigate('/settings#limits')}>上限設定</Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
          Codex + Workの日次トークンを使い、5時間参考上限を超えた回数相当と、月曜始まりの週次合計が週次参考上限を超えた回数相当を計算します。実際のリセット時刻やモデル別の重みは取得できないため、実際の到達回数ではありません。
        </Typography>
        <Grid container spacing={1.75}>
          <Grid size={{ xs: 12, md: 4 }}><Kpi label="5時間枠・到達相当" value={rows.length ? `${fmt(estimate.fiveHourHits)}回相当` : '—'} note={`参考上限 ${fmt(viewer.limits.fiveHour)} tokens`} /></Grid>
          <Grid size={{ xs: 12, md: 4 }}><Kpi label="週次枠・到達相当" value={rows.length ? `${fmt(estimate.weeklyHits)}回相当` : '—'} note={`${estimate.pressureWeeks}週が80%以上・上限 ${fmt(viewer.limits.weekly)}`} /></Grid>
          <Grid size={{ xs: 12, md: 4 }}><Kpi label="声かけ目安" value={rows.length ? estimate.level : '—'} note={rows.length ? estimate.reason : 'データ取込後に判定'} /></Grid>
        </Grid>
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">INDIVIDUAL TOKENS</Typography>
        <Typography variant="h2" sx={{ mb: 1 }}>製品別トークン消費量</Typography>
        <ProductLineChart rows={rows} metric="tokens" />
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline" color="warning.main">ANOMALY ANALYSIS</Typography>
        <Typography variant="h2" sx={{ mb: 1 }}>個人トークン異常分析</Typography>
        <AnomalyChart points={data?.analysis ?? []} narrowed={false} />
      </Paper>
      <IndividualTables rows={rows} limits={viewer.limits} />
    </Stack>
  )
}
