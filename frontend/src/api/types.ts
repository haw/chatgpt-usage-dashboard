export type Product = 'chat' | 'codex' | 'work'
export const PRODUCTS: Product[] = ['chat', 'codex', 'work']

export type Severity = 'high' | 'medium' | 'info'
export type DayKind = 'workday' | 'holiday'
export type DayKindSource = 'weekday' | 'weekend' | 'inferred' | 'override'

export interface ProductValues {
  chat: number
  codex: number
  work: number
}

export interface DailyRow {
  date: string
  end_date?: string
  active_users?: ProductValues
  tokens?: ProductValues & { total: number }
  day_kind: DayKind
  day_kind_source: DayKindSource
}

export interface Signal {
  detector: string
  type: string
  severity: Severity
  metric: string
  date: string
  value: number
  product: Product | null
  baseline: number | null
  threshold: number | null
  score: number | null
  reason: string
}

export interface AnalysisPoint {
  date: string
  value: number
  baseline: number | null
  threshold: number | null
  is_anomaly: boolean
  is_notable: boolean
  score: number | null
  kind: DayKind
}

export interface DetectorInfo {
  id: string
  label: string
  description: string
  group: string
  scopes: string[]
  params: Record<string, unknown>
  sensitivity_params: string[]
}

export interface ImportState {
  status?: string
  completed_at?: string
  start_date?: string
  end_date?: string
  imported_days?: number
  stored_days?: number
}

export interface Period {
  start_date: string | null
  end_date: string | null
}

export interface DashboardResponse {
  state: ImportState
  kpis: {
    latest_max_product_dau: number | null
    total_tokens: number | null
    daily_average_tokens: number | null
    alerts: number
  }
  daily: DailyRow[]
  alerts: Signal[]
  analysis: AnalysisPoint[]
  pending_days: number
  sensitivity: number
  detectors: DetectorInfo[]
  detector_errors: string[]
  available_period: Period
  selected_period: Period
}

export interface TriageObservation extends Signal {
  novel: boolean
  streak: number
}

export interface TriageEntry {
  date: string
  score: number
  detectors: number
  max_severity: Severity
  novel: boolean
  continuing: boolean
  streak: number
  facts: { kind: DayKind; kind_source: DayKindSource; max_dau: number | null; total_tokens: number | null }
  observations: TriageObservation[]
  disposition: { date: string; kind: string; recorded_at: string } | null
  tier: 'today' | 'week' | 'reference'
}

export interface TriageResponse {
  status: {
    latest_date: string | null
    as_of: string
    age_days: number | null
    stale: boolean
    stale_reason: string | null
    completed_at?: string
    stored_days: number
    pending_days: number
    baseline: string
    checked_days: number
  }
  today: TriageEntry[]
  week: TriageEntry[]
  reference: TriageEntry[]
  detector_errors: string[]
}

export interface ContextResponse {
  date: string
  rows: DailyRow[]
}

export interface Me {
  auth: 'none' | 'google'
  user: { email: string; name: string; picture?: string } | null
  domains: string[]
}

export interface ImportHistoryRow {
  run_id: string
  imported_at: string
  start_date: string | null
  end_date: string | null
  days: number
  active_users_bytes: number | null
  tokens_bytes: number | null
  active_users_sha256: string | null
  tokens_sha256: string | null
}

export interface IndividualUser {
  user_id: string
  user_label: string
  start_date: string
  end_date: string
  days: number
  total_tokens: number
}

export interface IndividualRow {
  date: string
  user_id: string
  user_label: string
  tokens: ProductValues & { total: number }
  day_kind: DayKind
  day_kind_source: DayKindSource
}

export interface IndividualResponse {
  state: ImportState & { user_label?: string }
  users: IndividualUser[]
  selected_user: IndividualUser | null
  daily: IndividualRow[]
  analysis: AnalysisPoint[]
  alerts: Signal[]
  detectors: DetectorInfo[]
  detector_errors: string[]
  product_totals: ProductValues
  kpis: { total_tokens: number; daily_average_tokens: number; latest_tokens: number; alerts: number }
}

export interface IndividualHistoryRow {
  run_id: string
  imported_at: string
  user_label: string
  start_date: string | null
  end_date: string | null
  days: number
  bytes: number
  sha256: string
}

export interface VersionInfo {
  /** `<semver>` or `<semver>+<first 8 characters of the deployed revision>` */
  version: string
  semver: string
  revision: string | null
}

export interface LicensePackage {
  name: string
  version: string
  license: string
  homepage: string
  text: string
}
