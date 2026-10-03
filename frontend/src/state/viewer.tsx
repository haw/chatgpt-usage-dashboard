import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

import type { DayKind } from '../api/types'

// Viewer-specific settings. They live in this browser only (same localStorage keys as the
// previous UI, so existing settings carry over) and travel with every request as parameters.

export const SENSITIVITY_STEPS = [
  { value: 0.5, label: '低' },
  { value: 0.7, label: 'やや低' },
  { value: 1, label: '標準' },
  { value: 1.4, label: 'やや高' },
  { value: 2, label: '高' },
] as const

export type ContextMode = 'box' | 'series' | 'both'
export type AiModel = 'webllm' | 'builtin' | 'auto'
export interface AiPrompts {
  system: string
  user: string
}

const KEYS = {
  sensitivity: 'chatgpt-dashboard.sensitivity.v1',
  overrides: 'chatgpt-dashboard.day-overrides.v1',
  contextMode: 'chatgpt-dashboard.context-mode.v1',
  aiModel: 'chatgpt-dashboard.ai-model.v1',
  aiPrompts: 'chatgpt-dashboard.ai-prompts.v1',
}

export const AI_DEFAULT_SYSTEM =
  '役割: 統計の知識がない担当者向けに、ChatGPT利用量ダッシュボードの1日分の判定結果を日本語で説明する。\n' +
  '制約: 与えられたJSONの数値だけを根拠にする。推測や、不正・悪意の断定はしない。専門用語（標準偏差・中央値・判定ライン）は使わず、「普段の何倍」「偶然では起きにくい」のような言葉に言い換える。3文以内、敬体。'
export const AI_DEFAULT_USER =
  '判定結果: {facts}\n「この日は何が普段と違うか」「どのくらい珍しいか」「次に何を確認するとよいか」を、この順で3文以内で書いてください。'
export const AI_EXPERT_SYSTEM =
  '役割: 統計に慣れた分析担当者向けに、ChatGPT利用量ダッシュボードの1日分の判定結果を日本語で簡潔に解説する。\n' +
  '前提: 各観点は、同じ区分（平日/休日）の直前28日を基準サンプルとし、中央値とMAD（中央絶対偏差、0.6745で割って標準偏差相当に換算）によるロバストZスコアで判定している。既に異常と判定した日は基準から除外している。sd はその日のロバストZスコア、threshold は判定ライン、usual は基準の中央値、ratio は中央値に対する倍率、streak は連続日数。\n' +
  '制約: 与えられたJSONの数値だけを根拠にする。不正・悪意の断定はしない。用語（ロバストZスコア、MAD、中央値、判定ライン）はそのまま使ってよい。基準サンプルが少ない（休日など）場合や、複数観点が同じ指標に由来する場合（総量と製品別、総量と1人あたり）は独立した証拠として数えない旨を一言添える。4文以内、常体。'
export const AI_EXPERT_USER =
  '判定結果: {facts}\n各観点のZスコアと倍率を根拠に、(1) 統計的にどの程度異常か、(2) 観点どうしの独立性と証拠の強さ、(3) 判定の限界（サンプル数・区分推定・継続の扱い）、(4) 次に確認すべきデータ、を4文以内で述べよ。'
export const AI_PRESETS: Record<'beginner' | 'expert', { label: string } & AiPrompts> = {
  beginner: { label: '統計の知識がない人向け', system: AI_DEFAULT_SYSTEM, user: AI_DEFAULT_USER },
  expert: { label: '統計に詳しい人向け', system: AI_EXPERT_SYSTEM, user: AI_EXPERT_USER },
}

function read<T>(key: string, parse: (raw: string) => T | null, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    return parse(raw) ?? fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown): boolean {
  try {
    localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

export function sensitivityIndex(value: number): number {
  return SENSITIVITY_STEPS.reduce(
    (best, step, index) => (Math.abs(step.value - value) < Math.abs(SENSITIVITY_STEPS[best].value - value) ? index : best),
    0,
  )
}

export function sensitivityLabel(value: number): string {
  return SENSITIVITY_STEPS[sensitivityIndex(value)].label
}

export interface ViewerState {
  sensitivity: number
  dayOverrides: Record<string, DayKind>
  contextMode: ContextMode
  aiModel: AiModel
  aiPrompts: AiPrompts
  setSensitivity: (value: number) => void
  toggleDayOverride: (date: string, autoKind: DayKind) => void
  removeDayOverride: (date: string) => void
  clearDayOverrides: () => void
  setContextMode: (mode: ContextMode) => void
  setAiModel: (model: AiModel) => void
  setAiPrompts: (prompts: AiPrompts) => boolean
  /** Query parameters every data request carries: sensitivity and the holiday/workday overrides. */
  params: { sensitivity?: number; holidays?: string; workdays?: string }
}

const ViewerContext = createContext<ViewerState | null>(null)

export function ViewerProvider({ children }: { children: ReactNode }) {
  const [sensitivity, setSensitivityState] = useState(() =>
    read(KEYS.sensitivity, (raw) => {
      const value = Number(raw)
      return value >= 0.25 && value <= 4 ? SENSITIVITY_STEPS[sensitivityIndex(value)].value : null
    }, 1),
  )
  const [dayOverrides, setDayOverrides] = useState<Record<string, DayKind>>(() =>
    read(
      KEYS.overrides,
      (raw) => {
        const saved = JSON.parse(raw)
        if (!saved || typeof saved !== 'object') return null
        return Object.fromEntries(
          Object.entries(saved).filter(([date, kind]) => /^\d{4}-\d{2}-\d{2}$/.test(date) && (kind === 'holiday' || kind === 'workday')),
        ) as Record<string, DayKind>
      },
      {},
    ),
  )
  const [contextMode, setContextModeState] = useState<ContextMode>(() =>
    read(KEYS.contextMode, (raw) => (['box', 'series', 'both'].includes(raw) ? (raw as ContextMode) : null), 'box'),
  )
  const [aiModel, setAiModelState] = useState<AiModel>(() =>
    read(KEYS.aiModel, (raw) => (['webllm', 'builtin', 'auto'].includes(raw) ? (raw as AiModel) : null), 'webllm'),
  )
  const [aiPrompts, setAiPromptsState] = useState<AiPrompts>(() =>
    read(
      KEYS.aiPrompts,
      (raw) => {
        const saved = JSON.parse(raw)
        return saved && typeof saved.system === 'string' && typeof saved.user === 'string' ? saved : null
      },
      { system: AI_DEFAULT_SYSTEM, user: AI_DEFAULT_USER },
    ),
  )

  const setSensitivity = useCallback((value: number) => {
    const snapped = SENSITIVITY_STEPS[sensitivityIndex(value)].value
    setSensitivityState(snapped)
    write(KEYS.sensitivity, String(snapped))
  }, [])
  const updateOverrides = useCallback((next: Record<string, DayKind>) => {
    setDayOverrides(next)
    write(KEYS.overrides, next)
  }, [])
  const toggleDayOverride = useCallback(
    (date: string, autoKind: DayKind) => {
      const next = { ...dayOverrides }
      if (next[date]) delete next[date]
      else next[date] = autoKind === 'holiday' ? 'workday' : 'holiday'
      updateOverrides(next)
    },
    [dayOverrides, updateOverrides],
  )
  const removeDayOverride = useCallback(
    (date: string) => {
      const next = { ...dayOverrides }
      delete next[date]
      updateOverrides(next)
    },
    [dayOverrides, updateOverrides],
  )
  const clearDayOverrides = useCallback(() => updateOverrides({}), [updateOverrides])
  const setContextMode = useCallback((mode: ContextMode) => {
    setContextModeState(mode)
    write(KEYS.contextMode, mode)
  }, [])
  const setAiModel = useCallback((model: AiModel) => {
    setAiModelState(model)
    write(KEYS.aiModel, model)
  }, [])
  const setAiPrompts = useCallback((prompts: AiPrompts) => {
    setAiPromptsState(prompts)
    return write(KEYS.aiPrompts, prompts)
  }, [])

  const params = useMemo(() => {
    const holidays = Object.keys(dayOverrides).filter((d) => dayOverrides[d] === 'holiday').sort().join(',')
    const workdays = Object.keys(dayOverrides).filter((d) => dayOverrides[d] === 'workday').sort().join(',')
    return {
      sensitivity: sensitivity !== 1 ? sensitivity : undefined,
      holidays: holidays || undefined,
      workdays: workdays || undefined,
    }
  }, [sensitivity, dayOverrides])

  const value = useMemo<ViewerState>(
    () => ({
      sensitivity, dayOverrides, contextMode, aiModel, aiPrompts,
      setSensitivity, toggleDayOverride, removeDayOverride, clearDayOverrides, setContextMode, setAiModel, setAiPrompts,
      params,
    }),
    [sensitivity, dayOverrides, contextMode, aiModel, aiPrompts, setSensitivity, toggleDayOverride, removeDayOverride, clearDayOverrides, setContextMode, setAiModel, setAiPrompts, params],
  )
  return <ViewerContext.Provider value={value}>{children}</ViewerContext.Provider>
}

export function useViewer(): ViewerState {
  const value = useContext(ViewerContext)
  if (!value) throw new Error('useViewer must be used inside ViewerProvider')
  return value
}
