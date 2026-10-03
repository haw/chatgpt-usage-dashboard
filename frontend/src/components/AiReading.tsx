import { Box, Button, LinearProgress, Stack, Typography } from '@mui/material'
import { useEffect, useState } from 'react'

import type { TriageEntry } from '../api/types'
import { dateLabel, signalSentence } from '../lib/format'
import { plainMetric } from '../lib/stats'
import { useViewer, type AiModel } from '../state/viewer'

const AI_MODEL = 'Qwen2.5-1.5B-Instruct-q4f16_1-MLC'
const AI_LIBRARY = 'https://esm.run/@mlc-ai/web-llm'

type Backend = 'builtin' | 'webllm'
interface Engine {
  kind: Backend
  system: string
  ask: (text: string) => Promise<string>
}

// Chrome's built-in Gemini Nano (Prompt API). Absent in other browsers.
interface LanguageModelStatic {
  availability: () => Promise<string>
  create: (options: unknown) => Promise<{ clone: () => Promise<{ prompt: (text: string) => Promise<string> }> }>
}
declare global {
  interface Window {
    LanguageModel?: LanguageModelStatic
  }
  interface Navigator {
    gpu?: unknown
  }
}

async function builtinAvailability(): Promise<string> {
  try {
    return window.LanguageModel ? await window.LanguageModel.availability() : 'unavailable'
  } catch {
    return 'unavailable'
  }
}

async function chooseBackend(preference: AiModel): Promise<Backend | null> {
  const builtin = await builtinAvailability()
  if (preference === 'builtin') return builtin !== 'unavailable' ? 'builtin' : null
  if (preference === 'webllm') return navigator.gpu ? 'webllm' : null
  return builtin !== 'unavailable' ? 'builtin' : navigator.gpu ? 'webllm' : null
}

let engine: Engine | null = null
let loading: Promise<Engine> | null = null

export interface Progress {
  text: string
  /** 0..1 while the model downloads; undefined when the share is unknown. */
  fraction?: number
}

async function loadEngine(backend: Backend, system: string, onProgress: (progress: Progress) => void): Promise<Engine> {
  if (engine && engine.kind === backend && engine.system === system) return engine
  if (engine && engine.kind === 'webllm' && backend === 'webllm') {
    engine.system = system // the prompt is passed per request; keep the 1GB model loaded
    return engine
  }
  if (!loading) {
    loading = (async () => {
      if (backend === 'builtin') {
        const session = await window.LanguageModel!.create({
          initialPrompts: [{ role: 'system', content: system }],
          expectedInputs: [{ type: 'text', languages: ['ja'] }],
          expectedOutputs: [{ type: 'text', languages: ['ja'] }],
          monitor(m: { addEventListener: (type: string, listener: (e: { loaded: number }) => void) => void }) {
            m.addEventListener('downloadprogress', (e) => onProgress({ text: `内蔵AIのモデルを取得中 ${Math.round(e.loaded * 100)}%`, fraction: e.loaded }))
          },
        })
        engine = { kind: 'builtin', system, ask: async (text) => (await session.clone()).prompt(text) }
        return engine
      }
      const webllm = await import(/* @vite-ignore */ AI_LIBRARY)
      const mlc = await webllm.CreateMLCEngine(AI_MODEL, { initProgressCallback: (p: { text: string; progress: number }) => onProgress({ text: p.text, fraction: p.progress }) })
      engine = {
        kind: 'webllm',
        system,
        ask: async (text) =>
          (await mlc.chat.completions.create({ messages: [{ role: 'system', content: engine!.system }, { role: 'user', content: text }], temperature: 0.2, max_tokens: 260 })).choices[0].message.content ?? '',
      }
      return engine
    })().finally(() => { loading = null })
  }
  return loading
}

function readingFacts(entry: TriageEntry) {
  const f = entry.facts
  return {
    date: dateLabel(entry.date),
    kind: f.kind === 'holiday' ? (f.kind_source === 'inferred' ? '平日だが利用が少なく休日と推定' : '休日') : '平日',
    dau: f.max_dau,
    total_tokens: f.total_tokens,
    observations: entry.observations.filter((o) => o.severity !== 'info').map((o) => ({
      what: plainMetric(o),
      detector: o.detector,
      sentence: signalSentence(o, f.kind),
      value: o.value, usual: o.baseline, threshold: o.threshold,
      ratio: o.baseline ? Math.round((o.value / o.baseline) * 10) / 10 : null,
      sd: o.score != null ? Math.round(Math.abs(o.score) * 10) / 10 : null,
      streak: o.streak,
    })),
    checked: Boolean(entry.disposition),
  }
}

/** Plain-language reading of a day, generated on demand by an in-browser model (trial). */
export default function AiReading({ entry }: { entry: TriageEntry }) {
  const { aiModel, aiPrompts } = useViewer()
  const [backend, setBackend] = useState<Backend | null>(null)
  const [status, setStatus] = useState('')
  const [progress, setProgress] = useState<Progress | null>(null)
  const [output, setOutput] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let cancelled = false
    setOutput('')
    setStatus('')
    chooseBackend(aiModel).then((b) => { if (!cancelled) { setBackend(b); if (!b) setStatus('AIを使えません（取込と設定のモデル設定を確認してください）') } })
    return () => { cancelled = true }
  }, [aiModel, entry.date])

  async function ask() {
    if (!backend) return
    setBusy(true)
    setStatus('')
    try {
      const model = await loadEngine(backend, aiPrompts.system, setProgress)
      setProgress({ text: '生成中…' })
      const text = aiPrompts.user.replace('{facts}', JSON.stringify(readingFacts(entry)))
      setOutput((await model.ask(text)).trim())
    } catch (error) {
      setStatus(`AIを使えませんでした: ${(error as Error).message}`)
    } finally {
      setProgress(null)
      setBusy(false)
    }
  }

  const strong = entry.observations.some((o) => o.severity !== 'info')
  return (
    <Box sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 2, bgcolor: '#fbfaf7' }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="subtitle2">読み取り</Typography>
        <Button size="small" variant="outlined" disabled={!backend || !strong || busy} onClick={ask}>
          {output ? 'もう一度問い合わせる' : 'AIに問い合わせる'}
        </Button>
        {status && <Typography variant="caption" color="text.secondary">{status}</Typography>}
      </Stack>
      {progress && (
        <Box sx={{ mt: 1 }}>
          <LinearProgress variant={progress.fraction != null ? 'determinate' : 'indeterminate'} value={progress.fraction != null ? Math.round(progress.fraction * 100) : undefined} sx={{ height: 6, borderRadius: 3 }} />
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>{progress.text}</Typography>
        </Box>
      )}
      {output && (
        <Typography variant="body2" sx={{ mt: 1, p: 1, borderLeft: 3, borderColor: 'primary.main', bgcolor: 'background.paper', lineHeight: 1.6 }}>
          {output}
        </Typography>
      )}
    </Box>
  )
}
