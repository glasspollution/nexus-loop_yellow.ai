import type { Finding, ImpactFigure, ScreenModel } from '../types'

function figure(definitionId: string, display: string, label: string): ImpactFigure {
  return {
    def: definitionId,
    display,
    label,
    definition: `Definition for ${label.toLowerCase()}.`,
    fidelity: 'derived',
    window: [4, 10],
  }
}

function finding(id: string, title: string, cost: string): Finding {
  return {
    finding_id: id,
    title,
    headline: `${title} affected the example cohort during the review window.`,
    severity: 'high',
    severity_label: 'High',
    tenant: 'Demo Tenant',
    slice: 'channel = sample',
    status: { state: 'ongoing', label: 'Backend-provided status', sentence: 'Backend-provided status sentence.' },
    impact: {
      figures: [
        figure('impact.exposed', '1,200', 'Conversations in the slice'),
        figure('impact.share', '12.0%', 'Share of tenant traffic'),
        figure('impact.hit', '320', 'Conversations actually hit'),
        figure('impact.extra_turns', '850', 'Extra turns'),
        figure('impact.cost_excess', cost, 'Extra spend against the baseline'),
        figure('impact.days_running', '10 days', 'Days running'),
        {
          ...figure('impact.mechanism', '7.0', 'Mechanism metric'),
          baseline: { label: 'Earlier comparable traffic', display: '4.5', n: 900 },
        },
      ],
      derivation: 'Window and baseline details supplied by the server.',
      harm: 'behaviour',
    },
    baseline: { label: 'Earlier comparable traffic', why: 'It was the closest stable comparison.', n: 900 },
    who_acts: [{ key: 'agent_builder', label: 'Agent builder' }],
    who_acts_why: 'The diagnosed change belongs to the agent configuration.',
    if_nothing_changes: 'Customers will continue spending longer in conversations that should finish sooner.',
    evidence: [{ line: 'The supplied metric moved away from its named baseline.' }],
    diagnosis: {
      label: 'Example configuration issue',
      confidence: 0.91,
      evidence: ['The change aligns with the affected window.'],
      config_change: { day: 7, target: 'agent-v2', from: 'p1', to: 'p2' },
    },
    standard: [],
    proposal: {
      prescription_id: `p-${id}`,
      proposal_sha: `sha-${id}`,
      label: 'Review a configuration change',
      description: 'Restore the previously successful behavior for this cohort.',
      decision: {
        asking_approval_for: 'Approve a guarded configuration adjustment.',
        risk_if_diagnosis_wrong: 'The change may not improve the affected conversations.',
        would_not_ship_if: 'The protected examples regress.',
        trade_off: 'The safer path may respond more slowly.',
      },
    },
    verification: null,
    approval: { state: 'pending', label: 'Awaiting a decision' },
  }
}

export const screenFixture: ScreenModel = {
  screen_version: 'nexus-loop-screen/1',
  built_at: '2026-01-14T10:30:00Z',
  source: { generated_report_sha256: 'generated-sha', report_sha256: 'report-sha', report_version: '1' },
  header: { team: 'Example Operations', corpus: 'Demo', tenants: ['Demo Tenant'], days: 28 },
  summary: {
    regressions: 2,
    dismissed: 1,
    refused_questions: 1,
    decisions_pending: 2,
    decisions_recorded: 0,
    needs_reconfirmation: [],
  },
  findings: [
    finding('f-1', 'Responses take too many turns', '$1,234.50'),
    finding('f-2', 'A lookup is not returning answers', '$245.00'),
  ],
  dismissed: [
    {
      finding_id: 'dismissed-1',
      tenant: 'Demo Tenant',
      slice: 'all traffic',
      window: { from_day: 8, to_day: 12 },
      cause_class: 'load',
      label: 'Backend traffic surge',
      why_not_a_problem: 'Backend analysis found that the signal ended when traffic returned to normal.',
      evidence: [
        'Backend evidence: latency moved across every cohort at once.',
        'Backend evidence: the deviation ended with the traffic surge.',
      ],
    },
  ],
  refusals: {},
  metrics: [],
  asks: [],
  standard: {},
  self_assessment: null,
  disclosures: {},
  labels: {},
  definitions: {},
}
