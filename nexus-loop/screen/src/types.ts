export type ImpactFigure = {
  def?: string
  display?: string | null
  value?: string | number | null
  label?: string | null
  unit?: string | null
  definition?: string | null
  fidelity?: string | null
  window?: Array<string | number> | null
  coverage?: number | string | null
  predicate?: string | null
  ci95?: Array<number | string> | null
  baseline?: {
    kind?: string | null
    label?: string | null
    n?: number | null
    display?: string | null
  } | null
  metric_definition?: {
    label?: string | null
    definition?: string | null
    unit?: string | null
    fidelity?: string | null
    coverage?: unknown
    calibration?: unknown
  } | null
}

export type ProposalDecision = {
  asking_approval_for?: string | null
  risk_if_diagnosis_wrong?: string | null
  would_not_ship_if?: string | null
  trade_off?: string | null
  why_no_action?: string | null
}

export type ProposalAlternative = {
  change_type?: string | null
  asking_approval_for?: string | null
  risk_if_diagnosis_wrong?: string | null
  trade_off?: string | null
  [key: string]: unknown
}

export type Verification = {
  prescription_id?: string | null
  replay_run_id?: string | null
  metric?: string | null
  metric_label?: string | null
  before?: string | number | null
  before_display?: string | null
  after?: string | number | null
  after_display?: string | null
  verdict?: string | null
  verdict_label?: string | null
  gate?: string | null
  gate_label?: string | null
  gate_reason?: string | null
  reason?: string | null
  simulated?: boolean | null
  simulation_note?: string | null
  no_effect_meaning?: string | null
  golden_set_pass?: boolean | null
  golden_set_version?: string | null
  golden_set_replayed?: number | null
  golden_set_regressed?: number | null
  sessions_replayed_simulated?: number | null
  replayed_window?: Array<string | number> | null
  predicted_delta?: string | number | null
  predicted_delta_display?: string | null
  observed_delta?: string | number | null
  observed_delta_display?: string | null
  prediction_error?: string | number | null
  prediction_error_display?: string | null
  request_sha256?: string | null
  from_cache?: boolean | null
  runs_used?: number | null
  definition?: Record<string, unknown> | string | null
  [key: string]: unknown
}

export type Finding = {
  finding_id: string
  title: string
  headline: string
  severity?: string | null
  severity_label?: string | null
  tenant?: string | null
  slice?: string | null
  status: {
    state?: string | null
    label?: string | null
    sentence?: string | null
  }
  impact: {
    figures: ImpactFigure[]
    derivation?: string | null
    harm?: string | null
  }
  baseline?: {
    label?: string | null
    why?: string | null
    n?: number | null
    kind?: string | null
  } | null
  who_acts?: Array<{ key?: string; label?: string | null }>
  who_acts_why?: string | null
  if_nothing_changes?: string | null
  evidence?: Array<Record<string, unknown> & { line?: string }>
  diagnosis?: {
    label?: string | null
    confidence?: string | number | null
    evidence?: string[]
    config_change?: Record<string, unknown> | null
  } | null
  standard?: Array<Record<string, unknown>>
  proposal?: {
    prescription_id: string
    fix_id?: string | null
    proposal_sha: string
    change_type?: string | null
    label?: string | null
    target?: string | null
    description?: string | null
    owner?: string | null
    autonomy_rung?: string | number | null
    decision?: ProposalDecision | null
    alternatives?: ProposalAlternative[]
    predicted_delta?: unknown
    replay_prediction?: unknown
    mechanism_prediction?: unknown
    standard_gap?: Array<Record<string, unknown>>
  } | null
  verification?: Verification | null
  approval?: {
    state?: 'pending' | 'accepted' | 'rejected' | 'deferred' | string
    label?: string | null
    decided_by?: string | null
    reason?: string | null
    at?: string | null
  } | null
}

export type DismissedFinding = {
  finding_id: string
  tenant?: string | null
  slice?: string | null
  window?: {
    from_day?: string | number | null
    to_day?: string | number | null
  } | null
  cause_class?: string | null
  label?: string | null
  why_not_a_problem?: string | null
  evidence?: string[]
}

export type ScreenModel = {
  screen_version: string
  built_at?: string | null
  source: {
    generated_report_sha256?: string | null
    report_sha256?: string | null
    report_version?: string | null
  }
  header: {
    team?: string | null
    corpus?: string | null
    tenants?: string[] | null
    days?: number | null
  }
  summary: {
    regressions: number
    dismissed?: number
    refused_questions?: number
    decisions_pending: number
    decisions_recorded?: number
    needs_reconfirmation?: unknown[]
  }
  findings: Finding[]
  dismissed?: DismissedFinding[]
  refusals?: Record<string, unknown>
  metrics?: Array<Record<string, unknown>>
  asks?: Array<Record<string, unknown>>
  standard?: Record<string, unknown>
  self_assessment?: Record<string, unknown> | null
  disclosures?: Record<string, string[]>
  labels?: Record<string, Record<string, string>>
  definitions?: Record<string, Record<string, unknown>>
  system_notes?: unknown
}

export type DecisionVerdict = 'accepted' | 'rejected' | 'deferred'

export type DecisionRequest = {
  prescription_id: string
  verdict: DecisionVerdict
  decided_by: string
  reason: string
  proposal_sha: string
  generated_report_sha256: string
}
