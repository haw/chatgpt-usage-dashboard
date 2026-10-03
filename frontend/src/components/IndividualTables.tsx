import { Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material'

import { PRODUCTS, type IndividualRow } from '../api/types'
import { fmt, weekdayOf } from '../lib/format'
import { buildWeeklyRows, limitInfo } from '../lib/quota'
import type { Limits } from '../state/viewer'
import { colors } from '../theme'

const STATUS_COLOR = { reached: colors.red, near: colors.warn, normal: colors.muted }
const percent = new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 1 })

function LimitCells({ value, limit }: { value: number; limit: number }) {
  const info = limitInfo(value, limit)
  return (
    <>
      <TableCell align="right">
        {percent.format(info.ratio)}%
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>上限 {fmt(limit)}</Typography>
      </TableCell>
      <TableCell><Chip size="small" label={info.label} sx={{ bgcolor: STATUS_COLOR[info.status], color: '#fff', fontWeight: 700, height: 20 }} /></TableCell>
    </>
  )
}

export default function IndividualTables({ rows, limits }: { rows: IndividualRow[]; limits: Limits }) {
  const weeks = buildWeeklyRows(rows)
  return (
    <>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">WEEKLY DATA</Typography>
        <Typography variant="h2" sx={{ mb: 1 }}>個人別週次データ</Typography>
        <TableContainer>
          <Table size="small" sx={{ minWidth: 760 }}>
            <TableHead>
              <TableRow><TableCell>週（月〜日）</TableCell><TableCell align="right">Chat</TableCell><TableCell align="right">Codex</TableCell><TableCell align="right">Work</TableCell><TableCell align="right">全体合計</TableCell><TableCell align="right">枠対象 Codex + Work</TableCell><TableCell align="right">週次枠消費率</TableCell><TableCell>到達情報</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {[...weeks].reverse().map((row) => (
                <TableRow key={row.start}>
                  <TableCell>{row.start} – {row.end}</TableCell>
                  {PRODUCTS.map((p) => <TableCell key={p} align="right">{fmt(row[p])}</TableCell>)}
                  <TableCell align="right"><strong>{fmt(row.total)}</strong></TableCell>
                  <TableCell align="right">{fmt(row.agentTokens)}</TableCell>
                  <LimitCells value={row.agentTokens} limit={limits.weekly} />
                </TableRow>
              ))}
              {!weeks.length && <TableRow><TableCell colSpan={8} align="center">データがありません</TableCell></TableRow>}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="overline">DAILY DATA</Typography>
        <Typography variant="h2" sx={{ mb: 1 }}>個人別日次データ</Typography>
        <TableContainer>
          <Table size="small" sx={{ minWidth: 760 }}>
            <TableHead>
              <TableRow><TableCell>日付・曜日</TableCell><TableCell align="right">Chat</TableCell><TableCell align="right">Codex</TableCell><TableCell align="right">Work</TableCell><TableCell align="right">全体合計</TableCell><TableCell align="right">枠対象 Codex + Work</TableCell><TableCell align="right">5時間枠消費率</TableCell><TableCell>到達情報</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {[...rows].reverse().map((row) => {
                const agent = row.tokens.codex + row.tokens.work
                const { label, day } = weekdayOf(row.date)
                return (
                  <TableRow key={row.date}>
                    <TableCell sx={{ whiteSpace: 'nowrap', color: row.day_kind === 'holiday' ? colors.red : 'inherit' }}>{row.date} <span style={{ fontWeight: 700, color: day === 0 ? '#b5443c' : day === 6 ? colors.codex : colors.muted }}>({label})</span></TableCell>
                    {PRODUCTS.map((p) => <TableCell key={p} align="right">{fmt(row.tokens[p])}</TableCell>)}
                    <TableCell align="right"><strong>{fmt(row.tokens.total)}</strong></TableCell>
                    <TableCell align="right">{fmt(agent)}</TableCell>
                    <LimitCells value={agent} limit={limits.fiveHour} />
                  </TableRow>
                )
              })}
              {!rows.length && <TableRow><TableCell colSpan={8} align="center">データがありません</TableCell></TableRow>}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </>
  )
}
