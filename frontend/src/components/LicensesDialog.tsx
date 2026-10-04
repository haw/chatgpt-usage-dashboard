import { Alert, Box, Button, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, Link, List, ListItemButton, Tab, Tabs, Typography } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { getJson } from '../api/client'
import type { LicensePackage } from '../api/types'

type Side = 'client' | 'server'

// The generated list is large and rarely opened: it is loaded as its own chunk on demand.
async function loadClientLicenses(): Promise<LicensePackage[]> {
  const { default: raw } = await import('../generated/third-party-licenses.json?raw')
  return JSON.parse(raw) as LicensePackage[]
}

function PackageList({ packages }: { packages: LicensePackage[] }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <List dense disablePadding>
      {packages.map((p) => {
        const key = `${p.name}@${p.version}`
        return (
          <Box key={key} sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <ListItemButton onClick={() => setOpen(open === key ? null : key)} aria-expanded={open === key} aria-label={`${p.name} ${p.version} ${p.license}`} sx={{ gap: 1.5, alignItems: 'baseline' }}>
              <Typography component="span" sx={{ fontWeight: 700, fontSize: '0.88rem' }}>{p.name}</Typography>
              <Typography component="span" variant="caption" color="text.secondary">{p.version}</Typography>
              <Typography component="span" variant="caption" sx={{ ml: 'auto', textAlign: 'right' }}>{p.license || 'ライセンス表記なし'}</Typography>
            </ListItemButton>
            <Collapse in={open === key} unmountOnExit>
              <Box sx={{ px: 2, pb: 1.5 }}>
                {p.homepage && <Link href={p.homepage} target="_blank" rel="noreferrer" variant="caption">{p.homepage}</Link>}
                <Box component="pre" sx={{ m: 0, mt: 0.75, p: 1.25, bgcolor: 'action.hover', borderRadius: 1, fontSize: '0.72rem', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 320, overflow: 'auto' }}>
                  {p.text || 'パッケージにライセンス文が同梱されていません。上のリンク先を参照してください。'}
                </Box>
              </Box>
            </Collapse>
          </Box>
        )
      })}
    </List>
  )
}

export default function LicensesDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [side, setSide] = useState<Side>('client')
  const client = useQuery({ queryKey: ['licenses', 'client'], queryFn: loadClientLicenses, staleTime: Infinity, enabled: open })
  const server = useQuery({ queryKey: ['licenses', 'server'], queryFn: () => getJson<{ packages: LicensePackage[] }>('/api/licenses').then((body) => body.packages), staleTime: Infinity, enabled: open })
  const current = side === 'client' ? client : server
  const count = (n: number | undefined) => (n === undefined ? '' : `（${n}）`)
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" aria-labelledby="licenses-title">
      <DialogTitle id="licenses-title">利用ライブラリのライセンス</DialogTitle>
      <Tabs value={side} onChange={(_, value: Side) => setSide(value)} sx={{ px: 3, borderBottom: 1, borderColor: 'divider' }}>
        <Tab value="client" label={`クライアント${count(client.data?.length)}`} />
        <Tab value="server" label={`サーバー${count(server.data?.length)}`} />
      </Tabs>
      <DialogContent sx={{ pt: 1.5, minHeight: 360 }}>
        {current.isError && <Alert severity="error">ライセンス情報を取得できませんでした。</Alert>}
        {current.isPending && <Typography variant="body2" color="text.secondary">読み込み中…</Typography>}
        {current.data && <PackageList packages={current.data} />}
        {side === 'client' && (
          <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1.5 }}>
            AIの読み取りを使うときだけ、ブラウザが次を取得します（同梱はしていません）:{' '}
            <Link href="https://github.com/mlc-ai/web-llm" target="_blank" rel="noreferrer">WebLLM</Link>（Apache-2.0）、{' '}
            <Link href="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct" target="_blank" rel="noreferrer">Qwen2.5-1.5B-Instruct</Link>（Apache-2.0）。
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>閉じる</Button>
      </DialogActions>
    </Dialog>
  )
}
