import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined'
import { Box, Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from '@mui/material'

import { PRODUCTS, type DailyRow, type Signal } from '../api/types'
import { formatOptional, signalSentence, sourceLabel, weekdayOf } from '../lib/format'
import { useViewer } from '../state/viewer'
import { colors } from '../theme'

const RANK: Record<Signal['severity'], number> = { high: 0, medium: 1, info: 2 }
const BADGE: Record<Signal['severity'], string> = { high: colors.red, medium: colors.warn, info: colors.muted }

export default function DailyTable({ rows, alerts }: { rows: DailyRow[]; alerts: Signal[] }) {
  const { toggleDayOverride } = useViewer()
  if (!rows.length) return <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>指定期間にデータがありません</Typography>
  return (
    <TableContainer>
      <Table size="small" sx={{ minWidth: 820 }}>
        <TableHead>
          <TableRow>
            <TableCell rowSpan={2}>日付・曜日</TableCell>
            <TableCell rowSpan={2}>
              <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                区分
                <Tooltip arrow title="土日は休日、平日はDAU（DAUがない日はトークン）が平日の中央値の半分以下なら休日と推定します。日付または区分をクリックすると手動で切り替えられ（休日は赤字）、設定はこのブラウザだけに保存されます。異常判定は同じ区分の日どうしで比較します。">
                  <HelpOutlineIcon sx={{ fontSize: 14, color: 'warning.main', cursor: 'help' }} />
                </Tooltip>
              </Box>
            </TableCell>
            <TableCell rowSpan={2}>兆候</TableCell>
            <TableCell colSpan={3} align="center">アクティブユーザー</TableCell>
            <TableCell colSpan={4} align="center">トークン</TableCell>
          </TableRow>
          <TableRow>
            {PRODUCTS.map((p) => <TableCell key={`u-${p}`} align="right">{p[0].toUpperCase() + p.slice(1)}</TableCell>)}
            {PRODUCTS.map((p) => <TableCell key={`t-${p}`} align="right">{p[0].toUpperCase() + p.slice(1)}</TableCell>)}
            <TableCell align="right">合計</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {[...rows].reverse().map((row) => {
            const holiday = row.day_kind === 'holiday'
            const auto = row.day_kind_source === 'override' ? (holiday ? 'workday' : 'holiday') : row.day_kind
            const dayAlerts = alerts.filter((a) => a.date === row.date)
            const top = dayAlerts.reduce<Signal['severity']>((best, a) => (RANK[a.severity] < RANK[best] ? a.severity : best), 'info')
            const { label, day } = weekdayOf(row.date)
            const dateColor = holiday ? colors.red : day === 0 ? '#b5443c' : day === 6 ? colors.codex : colors.muted
            const toggle = () => toggleDayOverride(row.date, auto)
            return (
              <TableRow key={row.date} hover>
                <TableCell onClick={toggle} sx={{ cursor: 'pointer', userSelect: 'none', color: holiday ? colors.red : 'inherit', fontWeight: holiday ? 700 : 400, whiteSpace: 'nowrap' }} title={`クリックで${holiday ? '平日' : '休日'}に切替（このブラウザだけに保存）`}>
                  {row.date} <span style={{ color: dateColor, fontWeight: 700 }}>({label})</span>
                </TableCell>
                <TableCell onClick={toggle} sx={{ cursor: 'pointer' }}>
                  <Chip
                    size="small"
                    label={<span>{holiday ? '休日' : '平日'}<small style={{ marginLeft: 4, fontWeight: 500 }}>{sourceLabel[row.day_kind_source]}</small></span>}
                    sx={{ bgcolor: holiday ? '#f6dcd7' : '#f0eee8', color: holiday ? colors.red : 'text.secondary', fontWeight: 700, border: row.day_kind_source === 'override' ? '1px solid #7faa97' : '1px solid transparent' }}
                  />
                </TableCell>
                <TableCell>
                  {dayAlerts.length > 0 && (
                    <Tooltip arrow title={<span style={{ whiteSpace: 'pre-line' }}>{dayAlerts.map((a) => signalSentence(a, row.day_kind)).join('\n')}</span>}>
                      <Chip size="small" label={dayAlerts.length} sx={{ bgcolor: BADGE[top], color: '#fff', fontWeight: 800, height: 20, cursor: 'help' }} />
                    </Tooltip>
                  )}
                </TableCell>
                {PRODUCTS.map((p) => <TableCell key={`u-${p}`} align="right">{formatOptional(row.active_users?.[p])}</TableCell>)}
                {PRODUCTS.map((p) => <TableCell key={`t-${p}`} align="right">{formatOptional(row.tokens?.[p])}</TableCell>)}
                <TableCell align="right"><strong>{formatOptional(row.tokens?.total)}</strong></TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </TableContainer>
  )
}
