import LoginIcon from '@mui/icons-material/Login'
import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material'
import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../state/auth'

export default function LoginPage() {
  const { me } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  useEffect(() => {
    if (me?.user || me?.auth === 'none') navigate('/', { replace: true })
  }, [me, navigate])

  const error = params.get('error')
  const domains = me?.domains?.length ? me.domains.map((d) => `@${d}`).join('、') : '社内ドメイン'
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ px: { xs: 3, md: 6 }, pt: 5, pb: 3, borderBottom: 1, borderColor: 'divider', background: 'linear-gradient(120deg,#faf6ec,#e5eee8)' }}>
        <Typography variant="overline">USAGE ANALYTICS</Typography>
        <Typography variant="h1">ChatGPT Usage Monitor</Typography>
        <Typography color="text.secondary">集計JSONから、普段と違う日を見つけ、推移と文脈を確かめます。</Typography>
      </Box>
      <Box component="main" sx={{ maxWidth: 520, mx: 'auto', my: '8vh', px: 3, width: '100%' }}>
        <Paper sx={{ p: 4 }}>
          <Stack spacing={2} sx={{ alignItems: 'center', textAlign: 'center' }}>
            <Typography variant="overline">SIGN IN</Typography>
            <Typography variant="h2">社内アカウントでログイン</Typography>
            {params.get('logged_out') && <Alert severity="success" sx={{ width: '100%' }}>ログアウトしました。Google アカウント自体からはログアウトしていません。</Alert>}
            {error === 'domain' && (
              <Alert severity="error" sx={{ width: '100%' }}>
                {params.get('email') || 'このアカウント'} は許可されたドメインではありません。別のアカウントでログインしてください。
              </Alert>
            )}
            {error === 'oauth' && (
              <Alert severity="error" sx={{ width: '100%' }}>
                ログインに失敗しました{params.get('detail') ? `（${params.get('detail')}）` : ''}。もう一度お試しください。
              </Alert>
            )}
            <Typography color="text.secondary">
              会社の Google Workspace アカウント（{domains}）でログインします。それ以外のアカウントは利用できません。
            </Typography>
            <Button href="/login/google" variant="contained" size="large" startIcon={<LoginIcon />}>
              Google でログイン
            </Button>
          </Stack>
        </Paper>
      </Box>
    </Box>
  )
}
