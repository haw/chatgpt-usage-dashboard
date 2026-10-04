import { Alert, Button, Chip, Grid, List, ListItem, Paper, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { useLocation } from 'react-router-dom'

import { getJson } from '../api/client'
import type { DetectorInfo, VersionInfo } from '../api/types'
import LicensesDialog from '../components/LicensesDialog'
import { dateLabel, fmt } from '../lib/format'
import { AI_DEFAULT_SYSTEM, AI_DEFAULT_USER, AI_PRESETS, DEFAULT_LIMITS, useViewer, type AiModel } from '../state/viewer'
import { colors } from '../theme'
import { CLIENT_VERSION } from '../version'

const MODEL_NOTE: Record<AiModel, string> = {
  webllm: 'Qwen2.5-1.5B-Instruct を WebGPU で実行します。初回に約1GBを取得しブラウザにキャッシュします。',
  builtin: 'Chrome の Prompt API（Gemini Nano）を使います。Chrome 148 以降、または chrome://flags で有効化が必要です。',
  auto: '内蔵AIが使えればそれを、無ければ Qwen を使います。',
}

export default function SettingsPage() {
  const viewer = useViewer()
  const location = useLocation()
  const detectors = useQuery({ queryKey: ['detectors'], queryFn: () => getJson<{ detectors: DetectorInfo[]; errors: string[] }>('/api/detectors'), staleTime: Infinity })
  const [system, setSystem] = useState(viewer.aiPrompts.system)
  const [user, setUser] = useState(viewer.aiPrompts.user)
  const [promptMessage, setPromptMessage] = useState<{ text: string; severity: 'success' | 'error' | 'info' } | null>(null)
  const [fiveHour, setFiveHour] = useState(String(viewer.limits.fiveHour))
  const [weekly, setWeekly] = useState(String(viewer.limits.weekly))
  const [limitMessage, setLimitMessage] = useState<{ text: string; severity: 'success' | 'error' } | null>(null)
  const serverVersion = useQuery({ queryKey: ['version'], queryFn: () => getJson<VersionInfo>('/api/version'), staleTime: Infinity })
  const [licensesOpen, setLicensesOpen] = useState(false)
  useEffect(() => {
    if (location.hash === '#limits') document.getElementById('limits')?.scrollIntoView({ behavior: 'smooth' })
  }, [location.hash])

  function savePrompts(event: FormEvent) {
    event.preventDefault()
    if (!system.trim() || !user.includes('{facts}')) {
      setPromptMessage({ text: 'システムプロンプトは必須、指示文には {facts} を含めてください。', severity: 'error' })
      return
    }
    const ok = viewer.setAiPrompts({ system: system.trim(), user })
    setPromptMessage(ok ? { text: 'このブラウザに保存しました。次の問い合わせから使います。', severity: 'success' } : { text: 'ブラウザへ保存できませんでした。', severity: 'error' })
  }
  function resetPrompts() {
    setSystem(AI_DEFAULT_SYSTEM)
    setUser(AI_DEFAULT_USER)
    viewer.setAiPrompts({ system: AI_DEFAULT_SYSTEM, user: AI_DEFAULT_USER })
    setPromptMessage({ text: '初期値に戻しました。', severity: 'success' })
  }
  function saveLimits(event: FormEvent) {
    event.preventDefault()
    const a = Number(fiveHour)
    const b = Number(weekly)
    if (!Number.isSafeInteger(a) || a < 1 || !Number.isSafeInteger(b) || b < 1) {
      setLimitMessage({ text: '上限は1以上の整数で指定してください。', severity: 'error' })
      return
    }
    setLimitMessage(viewer.setLimits({ fiveHour: a, weekly: b }) ? { text: 'このブラウザに保存しました。', severity: 'success' } : { text: 'ブラウザへ保存できませんでした。', severity: 'error' })
  }

  const overrideDates = Object.keys(viewer.dayOverrides).sort()
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Typography variant="overline">DAY KINDS</Typography>
            <Typography variant="h2">休日・平日の手動設定</Typography>
          </div>
          <Button size="small" variant="outlined" disabled={!overrideDates.length} onClick={viewer.clearDayOverrides}>すべて解除</Button>
        </Stack>
        <Typography variant="body2" color="text.secondary">自動判定を上書きした日の一覧です。「推移」の日次データ表で日付または区分をクリックすると追加されます。このブラウザだけに保存されます。</Typography>
        <List dense>
          {overrideDates.map((date) => (
            <ListItem key={date} sx={{ gap: 1.5 }} secondaryAction={<Button size="small" onClick={() => viewer.removeDayOverride(date)}>解除</Button>}>
              <span>{dateLabel(date)}</span>
              <Chip size="small" label={viewer.dayOverrides[date] === 'holiday' ? '休日' : '平日'} sx={{ bgcolor: viewer.dayOverrides[date] === 'holiday' ? '#f6dcd7' : '#f0eee8', color: viewer.dayOverrides[date] === 'holiday' ? colors.red : 'text.secondary', fontWeight: 700 }} />
            </ListItem>
          ))}
          {!overrideDates.length && <ListItem><Typography variant="body2" color="text.secondary">手動設定はありません。</Typography></ListItem>}
        </List>
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">DETECTORS</Typography>
        <Typography variant="h2">判定に使っている観点</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>設定は <code>config/detectors.toml</code> で変更でき、次の読み込みから反映されます。</Typography>
        {detectors.data?.errors.length ? <Alert severity="error" sx={{ mb: 1.5 }}>検知器の設定に問題があります: {detectors.data.errors.join(' / ')}</Alert> : null}
        <Grid container spacing={1.25}>
          {(detectors.data?.detectors ?? []).map((d) => (
            <Grid key={d.id} size={{ xs: 12, md: 6, lg: 4 }}>
              <Paper variant="outlined" sx={{ p: 1.5, height: '100%', fontSize: '0.82rem' }}>
                <strong>{d.label}</strong> <Typography component="span" variant="caption" color="text.secondary">{d.id}{d.group === 'operations' ? '・取込状態として表示' : ''}</Typography>
                <Typography variant="body2" sx={{ my: 0.75 }}>{d.description}</Typography>
                <Typography variant="caption" color="text.secondary">{Object.entries(d.params).map(([k, v]) => `${k}=${String(v)}`).join(' · ')}</Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">AI READING</Typography>
        <Typography variant="h2">AIの読み取りに使うモデル</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          インサイトの「グラフで見る」にある「読み取り」は、「AIに問い合わせる」を押したときだけ生成されます。AIはブラウザ内で動き、その日の判定データ（JSON）だけを受け取ります。データは外部へ送られません。AIの文は判断の材料であり、数値で確認してください。モデルとプロンプトの設定はこのブラウザだけに保存されます。
        </Typography>
        <ToggleButtonGroup size="small" exclusive value={viewer.aiModel} onChange={(_, value: AiModel | null) => value && viewer.setAiModel(value)} aria-label="AIモデル">
          <ToggleButton value="webllm">Qwen2.5 1.5B（WebGPU）</ToggleButton>
          <ToggleButton value="builtin">Chrome内蔵 Gemini Nano</ToggleButton>
          <ToggleButton value="auto">自動（内蔵があれば内蔵）</ToggleButton>
        </ToggleButtonGroup>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{MODEL_NOTE[viewer.aiModel]}</Typography>
        <Stack component="form" onSubmit={savePrompts} spacing={1.5} sx={{ mt: 2 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary">プリセット</Typography>
            {(Object.keys(AI_PRESETS) as Array<keyof typeof AI_PRESETS>).map((key) => (
              <Button key={key} size="small" variant="outlined" onClick={() => { setSystem(AI_PRESETS[key].system); setUser(AI_PRESETS[key].user); setPromptMessage({ text: `「${AI_PRESETS[key].label}」を読み込みました。内容を確認して「プロンプトを保存」を押すと使われます。`, severity: 'info' }) }}>
                {AI_PRESETS[key].label}
              </Button>
            ))}
          </Stack>
          <TextField label="システムプロンプト" multiline minRows={4} value={system} onChange={(e) => setSystem(e.target.value)} helperText="AIの役割と制約。数値だけを根拠にする・断定しない、などをここで決めます。" />
          <TextField label="指示文" multiline minRows={3} value={user} onChange={(e) => setUser(e.target.value)} helperText="{facts} の位置に、その日の判定データ（JSON）が入ります。" />
          {promptMessage && <Alert severity={promptMessage.severity}>{promptMessage.text}</Alert>}
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
            <Button variant="outlined" onClick={resetPrompts}>初期値に戻す</Button>
            <Button type="submit" variant="contained">プロンプトを保存</Button>
          </Stack>
        </Stack>
      </Paper>
      <Paper id="limits" sx={{ p: 2.5 }}>
        <Typography variant="overline">PERSONAL</Typography>
        <Typography variant="h2">個人別分析の参考上限</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>このブラウザだけに保存される個人設定です。OpenAIの正式な上限値ではなく、公開された利用実測から算出した参考値です。</Typography>
        <Stack component="form" onSubmit={saveLimits} spacing={1.5}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField label="5時間上限トークン" type="number" value={fiveHour} onChange={(e) => setFiveHour(e.target.value)} helperText={`初期値 ${fmt(DEFAULT_LIMITS.fiveHour)}（週次参考値の15.2%）`} slotProps={{ htmlInput: { min: 1, step: 1 } }} fullWidth />
            <TextField label="1週間上限トークン" type="number" value={weekly} onChange={(e) => setWeekly(e.target.value)} helperText={`初期値 ${fmt(DEFAULT_LIMITS.weekly)}（Business Standardの公開実測例）`} slotProps={{ htmlInput: { min: 1, step: 1 } }} fullWidth />
          </Stack>
          {limitMessage && <Alert severity={limitMessage.severity}>{limitMessage.text}</Alert>}
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
            <Button variant="outlined" onClick={() => { setFiveHour(String(DEFAULT_LIMITS.fiveHour)); setWeekly(String(DEFAULT_LIMITS.weekly)); viewer.setLimits(DEFAULT_LIMITS); setLimitMessage({ text: '初期値にリセットして保存しました。', severity: 'success' }) }}>初期値にリセット</Button>
            <Button type="submit" variant="contained">設定を保存</Button>
          </Stack>
        </Stack>
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <Typography variant="overline">ABOUT</Typography>
            <Typography variant="h2">バージョン情報</Typography>
          </div>
          <Button size="small" variant="outlined" onClick={() => setLicensesOpen(true)}>ライセンス情報</Button>
        </Stack>
        <Stack direction="row" spacing={5} sx={{ mt: 1.5 }}>
          {[
            { label: 'クライアント', value: CLIENT_VERSION },
            { label: 'サーバー', value: serverVersion.data?.version ?? (serverVersion.isError ? '取得できません' : '…') },
          ].map((item) => (
            <div key={item.label}>
              <Typography variant="caption" color="text.secondary" component="div">{item.label}</Typography>
              <Typography component="div" aria-label={`${item.label}のバージョン`} sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 700 }}>{item.value}</Typography>
            </div>
          ))}
        </Stack>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1, mb: 0 }}>+ の後ろは、配信されたリビジョン（コミット）の先頭8桁です。</Typography>
        <LicensesDialog open={licensesOpen} onClose={() => setLicensesOpen(false)} />
      </Paper>
    </Stack>
  )
}
