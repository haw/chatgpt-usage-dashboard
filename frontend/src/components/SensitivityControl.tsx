import HelpOutlineIcon from '@mui/icons-material/HelpOutlineOutlined'
import { Slider, Stack, Tooltip, Typography } from '@mui/material'

import { SENSITIVITY_STEPS, sensitivityIndex, useViewer } from '../state/viewer'

const HELP = (
  <div>
    <strong>感度とは</strong>
    <br />
    各日を「同じ区分（平日/休日）の直前28日」と比べ、普段からどれだけ離れていたら検出点にするかの基準です。トークン量は差ではなく「普段の何倍か」で比べ、日ごとの倍率のばらつき（標準偏差相当）の何個分離れているかを数えます。ばらつきの尺度には外れ値に引っ張られない中央絶対偏差（MAD）を使っています。
    <br />
    <br />
    <strong>段階と目安</strong>
    <br />
    総トークンのおおよその目安を（）内に示します。利用が安定しているときの値で、日々のばらつきが大きい時期はもっと上になります。
    <br />
    ・低（×7、普段の約10倍）: 桁違いの急増だけ
    <br />
    ・やや低（×5、約6倍）: 休日や全社イベント程度の揺れは無視したいとき
    <br />
    ・標準（×3.5、約4倍）: 不正のなかった期間ではほとんど反応しない水準。日常の確認はここ
    <br />
    ・やや高（×2.5、約3倍）: 特定の期間で何が起きたか探るとき
    <br />
    ・高（×1.75、約2倍）: よくある多めの日も検出点に。探索用
    <br />
    <br />
    動かすとグラフの判定ラインが引き直され、下に検出された日が出ます。「インサイト」の順位には影響しません。設定はこのブラウザにだけ保存されます。
  </div>
)

export default function SensitivityControl() {
  const { sensitivity, setSensitivity } = useViewer()
  const multiple = 3.5 / sensitivity
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
      <Typography variant="body2" color="text.secondary" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
        感度
        <Tooltip title={HELP} placement="bottom-end" arrow>
          <HelpOutlineIcon sx={{ fontSize: 16, color: 'warning.main', cursor: 'help' }} />
        </Tooltip>
      </Typography>
      <Typography variant="caption" color="text.secondary">低</Typography>
      <Slider
        aria-label="感度（低・やや低・標準・やや高・高）"
        min={0}
        max={SENSITIVITY_STEPS.length - 1}
        step={1}
        marks
        value={sensitivityIndex(sensitivity)}
        onChange={(_, value) => setSensitivity(SENSITIVITY_STEPS[value as number].value)}
        sx={{ width: 170, color: 'warning.main' }}
      />
      <Typography variant="caption" color="text.secondary">高</Typography>
      <Typography variant="body2" sx={{ fontWeight: 700, color: 'warning.main', whiteSpace: 'nowrap', minWidth: '9em' }}>
        判定: 標準偏差×{multiple.toFixed(sensitivity === 2 ? 2 : 1).replace(/\.0$/, '')}
      </Typography>
    </Stack>
  )
}
