import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { Dialog, DialogContent, DialogTitle, IconButton, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'

import { getJson } from '../api/client'
import type { ImportHistoryRow, IndividualHistoryRow } from '../api/types'
import { fileSize, fmt } from '../lib/format'

function Hash({ bytes, hash }: { bytes: number | null; hash: string | null }) {
  if (bytes == null || !hash) return <>—</>
  return (
    <Typography component="span" variant="caption" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
      {fileSize(bytes)}
      <Tooltip title={hash}>
        <code>{hash.slice(0, 12)}…{hash.slice(-12)}</code>
      </Tooltip>
      <IconButton size="small" aria-label="SHA-256をコピー" onClick={() => navigator.clipboard?.writeText(hash)}>
        <ContentCopyIcon sx={{ fontSize: 14 }} />
      </IconButton>
    </Typography>
  )
}

export default function ImportHistoryDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const overall = useQuery({ queryKey: ['imports'], queryFn: () => getJson<{ imports: ImportHistoryRow[] }>('/api/imports'), enabled: open })
  const individual = useQuery({ queryKey: ['individual-imports'], queryFn: () => getJson<{ imports: IndividualHistoryRow[] }>('/api/individual/imports'), enabled: open })
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>保存データ履歴</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>全体・個人のアップロード元JSONを一覧表示します。SHA-256はコピーできます。</Typography>
        <Typography variant="subtitle2">全体データ</Typography>
        <Table size="small" sx={{ mb: 3 }}>
          <TableHead>
            <TableRow><TableCell>取込日時</TableCell><TableCell>対象期間</TableCell><TableCell>日数</TableCell><TableCell>アクティブユーザーJSON</TableCell><TableCell>トークンJSON</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {(overall.data?.imports ?? []).map((row, index) => (
              <TableRow key={row.run_id}>
                <TableCell>{new Date(row.imported_at).toLocaleString('ja-JP')}{index === 0 ? ' （最新）' : ''}</TableCell>
                <TableCell>{row.start_date ?? '—'} – {row.end_date ?? '—'}</TableCell>
                <TableCell>{fmt(row.days)}日</TableCell>
                <TableCell><Hash bytes={row.active_users_bytes} hash={row.active_users_sha256} /></TableCell>
                <TableCell><Hash bytes={row.tokens_bytes} hash={row.tokens_sha256} /></TableCell>
              </TableRow>
            ))}
            {overall.data && !overall.data.imports.length && <TableRow><TableCell colSpan={5}>保存されたJSON履歴はありません</TableCell></TableRow>}
          </TableBody>
        </Table>
        <Typography variant="subtitle2">個人データ</Typography>
        <Table size="small">
          <TableHead>
            <TableRow><TableCell>取込日時</TableCell><TableCell>ユーザー</TableCell><TableCell>対象期間</TableCell><TableCell>日数</TableCell><TableCell>JSON</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {(individual.data?.imports ?? []).map((row) => (
              <TableRow key={row.run_id}>
                <TableCell>{new Date(row.imported_at).toLocaleString('ja-JP')}</TableCell>
                <TableCell>{row.user_label}</TableCell>
                <TableCell>{row.start_date ?? '—'} – {row.end_date ?? '—'}</TableCell>
                <TableCell>{fmt(row.days)}日</TableCell>
                <TableCell><Hash bytes={row.bytes} hash={row.sha256} /></TableCell>
              </TableRow>
            ))}
            {individual.data && !individual.data.imports.length && <TableRow><TableCell colSpan={5}>保存された個人JSON履歴はありません</TableCell></TableRow>}
          </TableBody>
        </Table>
      </DialogContent>
    </Dialog>
  )
}
