import LoginIcon from '@mui/icons-material/Login'
import LogoutIcon from '@mui/icons-material/Logout'
import { Button, Stack, Typography } from '@mui/material'

import { useAuth } from '../state/auth'

/** Signed-in account with a logout link; becomes a login link when the session is gone. */
export default function AccountChip() {
  const { me, sessionLost } = useAuth()
  if (sessionLost || (me?.auth === 'google' && !me.user)) {
    return (
      <Button href="/login" size="small" variant="outlined" startIcon={<LoginIcon />}>
        ログイン
      </Button>
    )
  }
  if (!me?.user) return null
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <Typography variant="body2" color="text.secondary">
        {me.user.email}
      </Typography>
      <Button href="/logout" size="small" variant="outlined" startIcon={<LogoutIcon />}>
        ログアウト
      </Button>
    </Stack>
  )
}
