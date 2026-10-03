import HistoryIcon from '@mui/icons-material/History'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { Alert, Button, Paper, Stack, Typography } from '@mui/material'
import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { postForm } from '../api/client'
import type { DashboardResponse } from '../api/types'
import { useViewer } from '../state/viewer'
import ImportHistoryDialog from './ImportHistoryDialog'

export default function UploadCard() {
  const viewer = useViewer()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ text: string; severity: 'success' | 'error' | 'info' } | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  async function upload(files: FileList | null) {
    const list = Array.from(files ?? [])
    if (!list.length) return
    if (list.length > 2) {
      setMessage({ text: '一度に選べるJSONは2ファイルまでです。', severity: 'error' })
      return
    }
    setBusy(true)
    setMessage({ text: 'JSONの形式を検証しています。', severity: 'info' })
    try {
      const form = new FormData()
      list.forEach((file) => form.append('files', file))
      const data = await postForm<DashboardResponse>('/api/import', form, viewer.params)
      await queryClient.invalidateQueries()
      setMessage({ text: `${data.state.imported_days}日分を取り込みました。`, severity: 'success' })
    } catch (error) {
      setMessage({ text: (error as Error).message, severity: 'error' })
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'center' }, justifyContent: 'space-between' }}>
        <div>
          <Typography variant="overline">IMPORT</Typography>
          <Typography variant="h2">管理画面のJSONを取り込む</Typography>
          <Typography variant="body2" color="text.secondary">
            JSONを選択すると、DAU・トークンの種類を自動判定し、取り込んだデータですぐに反映します。1ファイルだけでも、期間が異なっていても取り込めます。
          </Typography>
        </div>
        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          <input ref={input} type="file" accept=".json,application/json" multiple hidden onChange={(event) => upload(event.target.files)} />
          <Button variant="contained" startIcon={<UploadFileIcon />} disabled={busy} onClick={() => input.current?.click()}>
            {busy ? '取込中…' : 'アップロードして分析'}
          </Button>
          <Button variant="outlined" startIcon={<HistoryIcon />} onClick={() => setHistoryOpen(true)}>
            保存データ履歴
          </Button>
        </Stack>
      </Stack>
      {message && <Alert severity={message.severity} sx={{ mt: 2 }}>{message.text}</Alert>}
      <ImportHistoryDialog open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </Paper>
  )
}
