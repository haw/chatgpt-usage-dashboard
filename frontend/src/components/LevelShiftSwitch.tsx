import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined'
import { FormControlLabel, Stack, Switch, Tooltip, Typography } from '@mui/material'

import { useViewer } from '../state/viewer'

const HELP = (
  <div>
    <strong>続く変化も判定（水準の変化）</strong>
    <br />
    1日ごとの判定に加えて、「普段より多い日が続いている」ことを見ます。毎日の普段からのずれを積み上げ、多めの日が続いて合計が一定を超えたら、始まりの日に「水準の変化」として1回だけ知らせます。以後はその新しい水準を基準にするので、同じ理由での検出は続きません。
    <br />
    <br />
    1日では判定ラインを超えない量が何日も続く不正（毎日少しずつ使う）に気づくための判定です。一方、利用が伸びている時期は「水準が上がった」が何度も出て、要確認の日が増えます。結果は過去の判定にも左右されるので、感度を変えたり新しい日が加わったりすると、さかのぼって項目が現れることがあります。
    <br />
    <br />
    推移・インサイト・個人別に共通で効き、このブラウザにだけ保存されます。
  </div>
)

/** Viewer's opt-in for the level-shift judgement; the API gets it as level_shifts=true. */
export default function LevelShiftSwitch() {
  const { levelShifts, setLevelShifts } = useViewer()
  return (
    <Stack direction="row" sx={{ alignItems: 'center', gap: 0.25 }}>
      <FormControlLabel
        control={<Switch size="small" checked={levelShifts} onChange={(_, on) => setLevelShifts(on)} slotProps={{ input: { 'aria-label': '続く変化も判定' } }} />}
        label={<Typography variant="body2" color="text.secondary">続く変化も判定</Typography>}
        sx={{ mr: 0 }}
      />
      <Tooltip title={HELP} placement="bottom-end" arrow>
        <HelpOutlineIcon sx={{ fontSize: 16, color: 'warning.main', cursor: 'help' }} />
      </Tooltip>
    </Stack>
  )
}
