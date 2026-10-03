import { Box, Container, Tab, Tabs, Typography } from '@mui/material'
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import AccountChip from './components/AccountChip'
import IndividualPage from './pages/IndividualPage'
import InsightsPage from './pages/InsightsPage'
import LoginPage from './pages/LoginPage'
import SettingsPage from './pages/SettingsPage'
import TrendsPage from './pages/TrendsPage'

// One path per view, so the browser back button and deep links work.
const VIEWS = [
  { path: '/', label: '推移' },
  { path: '/insights', label: 'インサイト' },
  { path: '/individual', label: '個人別' },
  { path: '/settings', label: '取込と設定' },
]

function currentView(pathname: string): string {
  if (pathname.startsWith('/insights')) return '/insights'
  if (pathname.startsWith('/individual')) return '/individual'
  if (pathname.startsWith('/settings')) return '/settings'
  return '/'
}

export default function App() {
  const location = useLocation()
  if (location.pathname === '/login') return <LoginPage />
  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Box
        component="header"
        sx={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 3, flexWrap: 'wrap',
          px: { xs: 3, md: 6 }, pt: 5, pb: 3, borderBottom: 1, borderColor: 'divider',
          background: 'linear-gradient(120deg,#faf6ec,#e5eee8)',
        }}
      >
        <div>
          <Typography variant="overline">USAGE ANALYTICS</Typography>
          <Typography variant="h1">ChatGPT Usage Monitor</Typography>
          <Typography color="text.secondary">集計JSONから、普段と違う日を見つけ、推移と文脈を確かめます。</Typography>
        </div>
        <AccountChip />
      </Box>
      <Container maxWidth="xl" component="main" sx={{ py: 3, flex: 1 }}>
        <Tabs value={currentView(location.pathname)} sx={{ mb: 2 }} aria-label="画面">
          {VIEWS.map((view) => (
            <Tab key={view.path} value={view.path} label={view.label} component={Link} to={view.path} />
          ))}
        </Tabs>
        <Routes>
          <Route path="/" element={<TrendsPage />} />
          <Route path="/trends" element={<Navigate to="/" replace />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/insights/:date" element={<InsightsPage />} />
          <Route path="/individual" element={<IndividualPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Container>
      <Box component="footer" sx={{ px: { xs: 3, md: 6 }, py: 2, borderTop: 1, borderColor: 'divider', color: 'text.secondary', fontSize: '0.72rem' }}>
        表示は推定であり、不正利用や制限到達を断定するものではありません。
      </Box>
    </Box>
  )
}
