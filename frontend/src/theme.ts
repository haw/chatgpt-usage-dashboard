import { createTheme } from '@mui/material/styles'

// The palette carries over from the previous static UI so the two look alike during the migration.
export const colors = {
  chat: '#176b4d',
  codex: '#3478a4',
  work: '#d49a31',
  red: '#a9483e',
  warn: '#ad5c19',
  ink: '#17231d',
  muted: '#69736d',
  line: '#ddd9cf',
  bg: '#f3f1eb',
  card: '#fffdfa',
}

export const theme = createTheme({
  palette: {
    primary: { main: colors.chat },
    secondary: { main: colors.codex },
    error: { main: colors.red },
    warning: { main: colors.warn },
    background: { default: colors.bg, paper: colors.card },
    text: { primary: colors.ink, secondary: colors.muted },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: 'Inter, "Noto Sans JP", system-ui, sans-serif',
    h1: { fontSize: '2.2rem', fontWeight: 700, letterSpacing: '-0.04em' },
    h2: { fontSize: '1.15rem', fontWeight: 700 },
    overline: { fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.17em', color: colors.muted },
  },
  components: {
    MuiPaper: { styleOverrides: { root: { border: `1px solid ${colors.line}`, boxShadow: '0 12px 34px #1c2c230d' } } },
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { textTransform: 'none', fontWeight: 700 } } },
    MuiTableCell: { styleOverrides: { root: { fontSize: '0.78rem', padding: '8px 10px' } } },
  },
})
