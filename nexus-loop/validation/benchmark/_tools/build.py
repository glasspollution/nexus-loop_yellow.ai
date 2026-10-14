#!/usr/bin/env python
"""Blind benchmark builder. Copies a source kit and injects novel faults + benign events.
Positions/params live in SPECS below and are written only to the answer key."""
import json, gzip, random, shutil, os, sys, math, datetime as dt, collections

UTC = dt.timezone.utc
EPOCH = dt.datetime(2026, 6, 1, tzinfo=UTC)
HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SCR = os.environ.get("NEXUS_BENCH_SCRATCH", os.path.join(WORKSPACE, "tmp", "benchmark-scratch"))
BENCH = os.environ.get("NEXUS_BENCH_OUT", os.path.join(SCR, "bench"))
SRC = {
    'A': (os.path.join(WORKSPACE, 'kit'), 'ground_truth/ground_truth.json', 'variant A'),
    'S2': (SCR + '/work/kit-s2', 'ground_truth_SEALED/ground_truth.json', 'kit-s2'),
}
PREFIX = ['session_id', 'tenant', 'step_seq', 'ts', 'day', 'step_type', 'agent_id', 'agent_kind', 'channel',
          'intent', 'model', 'prompt_version', 'kb_version']

# ----------------------------------------------------------------------------------------------
SPECS = [
 {'corpus': 'bench-01', 'split': 'dev', 'source': 'A', 'seed': 1101,
  'novel': [
   dict(id='N1', type='tool_outage', tenant='acme-bank', cohort={'tool': 'get_loan_status', 'intent': 'loan_status'},
        onset_day=12, duration_days=9, shape='step', magnitude_tier='large',
        handler='tool_errors', params=dict(tool='get_loan_status', p=0.30, mix={'5xx': 0.6, 'timeout': 0.4}, flip_p=0.7, handoff_share=0.65),
        metric=['tool_error_rate', 'get_loan_status'], primary_metric='tool error rate on get_loan_status',
        config=[(12, 'tool', 'get_loan_status', 'AUTO', '1.1.0', 'loan core API cutover'),
                (21, 'tool', 'get_loan_status', '1.1.0', '1.1.1', 'hotfix connection pool exhaustion')],
        versions=[dict(field='tool_version', tool='get_loan_status', intent='loan_status', value='1.1.0', from_day=12, to_day=20),
                  dict(field='tool_version', tool='get_loan_status', intent='loan_status', value='1.1.1', from_day=21, to_day=55)],
        accepted_cause_classes=['tool.outage'],
        description='get_loan_status starts failing (503s and ~5-12s timeouts) on ~30% of calls after a loan-core API cutover; most affected sessions end in unplanned handoff or abandonment. Fixed by a hotfix on day 21.'),
   dict(id='N2', type='guardrail_overblocking', tenant='northwind-retail', cohort={'intent': 'account_update'},
        onset_day=20, duration_days=12, shape='ramp', ramp_days=6, magnitude_tier='medium',
        handler='guardrail', params=dict(p=0.12, names={'pii_redaction': 0.8, 'toxicity': 0.2}, flip_p=0.45),
        metric=['guardrail_session_share'], primary_metric='share of account_update sessions with a guardrail block',
        config=[], versions=[], accepted_cause_classes=['unknown'],
        description='PII-redaction guardrail gradually starts false-positive blocking account_update conversations (addresses/phone numbers are legitimate there); ~45% of newly blocked sessions fail. No config marker.'),
   dict(id='N3', type='llm_latency_regression', tenant='northwind-retail', cohort={'agent_id': 'nw_returns_v3'},
        onset_day=32, duration_days=16, shape='step', magnitude_tier='subtle',
        handler='llm_latency', params=dict(factor=1.12, flip_p=0.01),
        metric=['llm_latency_mean', 'nw_returns_v3'], primary_metric='mean llm_call duration_ms on nw_returns_v3',
        config=[(32, 'model', 'nw_returns_v3', 'AUTO', 'sonnet-5', 'planned model upgrade')],
        versions=[dict(field='model', agent='nw_returns_v3', value='sonnet-5', from_day=32, to_day=55)],
        accepted_cause_classes=['model.change'],
        description='After a model upgrade on nw_returns_v3, llm_call latency rises ~12% (provider capacity) until day 48 when it recovers; the model stays upgraded. Tiny abandonment effect.'),
   dict(id='N4', type='channel_breakage', tenant='acme-bank', cohort={'channel': 'app'},
        onset_day=36, duration_days=7, shape='step', magnitude_tier='large',
        handler='channel_abandon', params=dict(p=0.25),
        metric=['abandon_rate'], primary_metric='abandonment rate on channel app',
        config=[], versions=[], accepted_cause_classes=['unknown'],
        description='A broken mobile app release drops the chat session mid-conversation: ~25% of otherwise-resolved app conversations end abandoned. Other channels unaffected. No config marker (app releases are not in the config timeline).'),
  ],
  'benign': [
   dict(id='B1', type='holiday_volume_drop', tenant='*', cohort={}, onset_day=7, duration_days=2,
        handler='holiday', params=dict(p=0.65), metric=['volume'],
        description='Public holiday: ~65% of sessions on both tenants disappear for two days; per-cohort rates unchanged.'),
  ]},
 {'corpus': 'bench-02', 'split': 'test', 'source': 'A', 'seed': 2202,
  'novel': [
   dict(id='N1', type='tool_latency_degradation', tenant='northwind-retail', cohort={'tool': 'reschedule_delivery', 'intent': 'delivery_reschedule'},
        onset_day=22, duration_days=10, shape='step', magnitude_tier='large',
        handler='tool_latency', params=dict(tool='reschedule_delivery', factor=3.5, flip_p=0.05),
        metric=['tool_latency_mean', 'reschedule_delivery'], primary_metric='mean tool_call duration_ms on reschedule_delivery',
        config=[(22, 'tool', 'reschedule_delivery', 'AUTO', '2.0.0', 'carrier slot API v2 migration'),
                (32, 'tool', 'reschedule_delivery', '2.0.0', '2.0.1', 'performance patch slot query index')],
        versions=[dict(field='tool_version', tool='reschedule_delivery', intent='delivery_reschedule', value='2.0.0', from_day=22, to_day=31),
                  dict(field='tool_version', tool='reschedule_delivery', intent='delivery_reschedule', value='2.0.1', from_day=32, to_day=55)],
        accepted_cause_classes=['tool.outage'],
        description='reschedule_delivery gets ~3.5x slower (no error outcomes) after a carrier API migration; session durations stretch and a few users abandon. Patched day 32.'),
   dict(id='N2', type='segment_regression', tenant='acme-bank', cohort={'segment': 'priority'},
        onset_day=8, duration_days=10, shape='ramp', ramp_days=6, magnitude_tier='medium',
        handler='unplanned_handoff', params=dict(p=0.28, groups={'specialist': 1.0}, max_k=3),
        metric=['resolution_rate'], primary_metric='resolution rate for segment priority',
        config=[], versions=[], accepted_cause_classes=['unknown', 'routing.error'],
        description='Priority-segment customers are increasingly pushed to a specialist desk early in the conversation (a CRM entitlement flag change); resolution falls only for that segment, across all agents and intents. No config marker.'),
   dict(id='N3', type='llm_retry_storm', tenant='acme-bank', cohort={'agent_id': 'acme_cards_v3'},
        onset_day=42, duration_days=8, shape='step', magnitude_tier='medium',
        handler='retry_storm', params=dict(p=0.08, reason='quality_retry', flip_p=0.03),
        metric=['llm_retry_share', 'acme_cards_v3'], primary_metric='share of llm_call rows that are retries on acme_cards_v3',
        config=[(42, 'prompt', 'acme_cards_v3', 'AUTO', 'p_v5', 'structured JSON reply format'),
                (50, 'prompt', 'acme_cards_v3', 'p_v5', 'p_v4', 'revert structured reply format')],
        versions=[dict(field='prompt_version', agent='acme_cards_v3', value='p_v5', from_day=42, to_day=49)],
        accepted_cause_classes=['prompt.regression'],
        description='A structured-output prompt on acme_cards_v3 fails output validation and triggers quality retries on ~8% of LLM calls; cost and latency up, resolution slightly down. Reverted day 50.'),
   dict(id='N4', type='milestone_funnel_break', tenant='northwind-retail', cohort={'intent': 'return_initiate'},
        onset_day=44, duration_days=6, shape='step', magnitude_tier='large',
        handler='funnel_stall', params=dict(p=0.5, tool='initiate_return', stage='item_chosen', abandon_share=0.6),
        metric=['milestone_reach_rate', 'return_created'], primary_metric='share of return_initiate sessions reaching milestone return_created',
        config=[], versions=[], accepted_cause_classes=['unknown'],
        description='Half of return journeys stall after item_chosen (return never created, initiate_return never called); users abandon or get handed off. No error outcomes, no config marker.'),
  ],
  'benign': [
   dict(id='B2', type='instrumentation_coverage_change', tenant='northwind-retail', cohort={'agent_id': 'nw_care_v3'},
        onset_day=30, duration_days=26, handler='drop_step_type', params=dict(agent='nw_care_v3', step_type='kb_lookup'),
        metric=['steps_per_session', 'nw_care_v3', 'kb_lookup'],
        description='Logging sampler change: nw_care_v3 stops emitting kb_lookup step rows from day 30. Session outcomes and session-level kb_miss_count are unchanged; this is a telemetry coverage change, not a quality change.'),
  ]},
 {'corpus': 'bench-03', 'split': 'dev', 'source': 'S2', 'seed': 3303,
  'novel': [
   dict(id='N1', type='handoff_misfire', tenant='acme-bank', cohort={'agent_id': 'acme_lending_v3'},
        onset_day=26, duration_days=11, shape='step', magnitude_tier='large',
        handler='unplanned_handoff', params=dict(p=0.30, groups={'tier1': 0.6, 'tier2': 0.4}, max_k=3),
        metric=['unplanned_handoff_rate'], primary_metric='unplanned handoff rate on acme_lending_v3',
        config=[(26, 'routing', 'acme_lending_v3', 'rr_v4', 'rr_v5', 'escalation confidence threshold retune'),
                (37, 'routing', 'acme_lending_v3', 'rr_v5', 'rr_v4', 'rollback escalation threshold')],
        versions=[], accepted_cause_classes=['routing.error'],
        description='A routing threshold retune on acme_lending_v3 escalates ~30% of conversations that would have resolved to a human within the first 1-3 turns (handoff_by_design=false). Rolled back day 37.'),
   dict(id='N2', type='tool_outage', tenant='northwind-retail', cohort={'tool': 'check_stock', 'intent': 'product_availability'},
        onset_day=8, duration_days=9, shape='ramp', ramp_days=6, magnitude_tier='subtle',
        handler='tool_errors', params=dict(tool='check_stock', p=0.055, mix={'5xx': 0.8, 'timeout': 0.2}, flip_p=0.6, handoff_share=0.5),
        metric=['tool_error_rate', 'check_stock'], primary_metric='tool error rate on check_stock',
        config=[], versions=[], accepted_cause_classes=['tool.outage', 'unknown'],
        description='Inventory service slowly degrades: check_stock 5xx/timeouts ramp up to ~+5.5pts over 6 days. No config marker.'),
   dict(id='N3', type='model_provider_errors', tenant='northwind-retail', cohort={'agent_id': 'nw_orders_v3'},
        onset_day=48, duration_days=8, shape='step', magnitude_tier='medium',
        handler='provider_errors', params=dict(p=0.09, lat_factor=1.4, flip_p=0.3),
        metric=['llm_error_rate', 'nw_orders_v3'], primary_metric='llm_call error rate on nw_orders_v3',
        config=[(48, 'model', 'nw_orders_v3', 'AUTO', 'sonnet-5', 'planned model upgrade')],
        versions=[dict(field='model', agent='nw_orders_v3', value='sonnet-5', from_day=48, to_day=55)],
        accepted_cause_classes=['model.change'],
        description='After a model upgrade on nw_orders_v3 the provider returns errors on ~9% of calls (each retried) and latency rises ~40%; some sessions give up.'),
   dict(id='N4', type='tool_breaking_change_4xx', tenant='acme-bank', cohort={'tool': 'raise_dispute', 'intent': 'txn_dispute'},
        onset_day=47, duration_days=9, shape='step', magnitude_tier='large',
        handler='tool_errors', params=dict(tool='raise_dispute', p=0.40, mix={'4xx': 1.0}, flip_p=0.75, handoff_share=0.7),
        metric=['tool_error_rate', 'raise_dispute'], primary_metric='tool error rate on raise_dispute',
        config=[(47, 'tool', 'raise_dispute', 'AUTO', '2.0.0', 'dispute API v2 reason_code now mandatory')],
        versions=[dict(field='tool_version', tool='raise_dispute', intent='txn_dispute', value='2.0.0', from_day=47, to_day=55)],
        accepted_cause_classes=['tool.contract_break', 'tool.outage'],
        description='Dispute API v2 makes a field mandatory that the agent does not send: 40% of raise_dispute calls return declared HTTP 422 (upstream.client_4xx); disputes are not raised.'),
  ],
  'benign': [
   dict(id='B3', type='channel_mix_shift', tenant='northwind-retail', cohort={'channel': 'app'},
        onset_day=22, duration_days=9, handler='clone_channel', params=dict(channel='app', extra_ratio=1.5),
        metric=['channel_share', 'app'],
        description='In-app order-tracking push campaign: app-channel traffic is 2.5x normal for 9 days. Added sessions behave exactly like normal app sessions of the same day.'),
  ]},
 {'corpus': 'bench-04', 'split': 'test', 'source': 'S2', 'seed': 4404,
  'novel': [
   dict(id='N1', type='context_overflow', tenant='acme-bank', cohort={'agent_id': 'acme_cards_v3'},
        onset_day=30, duration_days=5, shape='step', magnitude_tier='medium',
        handler='context_overflow', params=dict(p=0.55, min_turn=5, handoff_share=0.7),
        metric=['resolution_rate'], primary_metric='resolution rate on acme_cards_v3 (secondary: llm error rate model.context_overflow)',
        config=[(30, 'prompt', 'acme_cards_v3', 'AUTO', 'p_v5', 'full card terms appended to system prompt'),
                (35, 'prompt', 'acme_cards_v3', 'p_v5', 'p_v4', 'revert terms appendix')],
        versions=[dict(field='prompt_version', agent='acme_cards_v3', value='p_v5', from_day=30, to_day=34)],
        accepted_cause_classes=['prompt.regression'],
        description='A much longer system prompt on acme_cards_v3 makes long conversations (turn>=5) overflow the context window (llm_call error model.context_overflow); those sessions end in handoff/abandonment. Reverted day 35.'),
   dict(id='N2', type='channel_breakage', tenant='northwind-retail', cohort={'channel': 'whatsapp'},
        onset_day=21, duration_days=14, shape='ramp', ramp_days=10, magnitude_tier='subtle',
        handler='channel_abandon', params=dict(p=0.045),
        metric=['abandon_rate'], primary_metric='abandonment rate on channel whatsapp',
        config=[], versions=[], accepted_cause_classes=['unknown'],
        description='WhatsApp Business API message delivery delays grow over 10 days; a few extra percent of whatsapp conversations are abandoned mid-way. No config marker.'),
   dict(id='N3', type='handoff_misfire', tenant='northwind-retail', cohort={'agent_id': 'nw_returns_v3'},
        onset_day=38, duration_days=12, shape='step', magnitude_tier='subtle',
        handler='unplanned_handoff', params=dict(p=0.035, groups={'tier1': 0.5, 'tier2': 0.3, 'specialist': 0.2}, max_k=3),
        metric=['unplanned_handoff_rate'], primary_metric='unplanned handoff rate on nw_returns_v3',
        config=[(38, 'routing', 'nw_returns_v3', 'rr_v3', 'rr_v4', 'handoff confidence threshold raised')],
        versions=[], accepted_cause_classes=['routing.error'],
        description='Raised handoff threshold on nw_returns_v3 escalates ~3.5% of otherwise-resolved conversations early (measured lift also contains ~1pt from planted F2, whose order_status slice overlaps this agent in days 33-47). Not rolled back inside the corpus, but the fault window is closed at day 49 (weekly routing re-tune restored behaviour without a logged change).'),
   dict(id='N4', type='tool_outage', tenant='acme-bank', cohort={'tool': 'block_card', 'intent': 'card_block'},
        onset_day=13, duration_days=8, shape='step', magnitude_tier='medium',
        handler='tool_errors', params=dict(tool='block_card', p=0.10, mix={'timeout': 1.0}, flip_p=0.6, handoff_share=0.7),
        metric=['tool_error_rate', 'block_card'], primary_metric='tool error rate on block_card',
        config=[(13, 'tool', 'block_card', 'AUTO', '1.1.0', 'card processor client upgrade'),
                (21, 'tool', 'block_card', '1.1.0', '1.1.1', 'timeout config fix')],
        versions=[dict(field='tool_version', tool='block_card', intent='card_block', value='1.1.0', from_day=13, to_day=20),
                  dict(field='tool_version', tool='block_card', intent='card_block', value='1.1.1', from_day=21, to_day=55)],
        accepted_cause_classes=['tool.outage'],
        description='A card-processor client upgrade makes ~10% of block_card calls time out (5-12s); affected sessions mostly hand off. Fixed day 21.'),
  ],
  'benign': [
   dict(id='B4', type='new_agent_launch', tenant='acme-bank', cohort={'agent_id': 'acme_wealth_v3'},
        onset_day=12, duration_days=12, handler='reassign', params=dict(src_agents=['acme_cards_v3', 'acme_lending_v3'], new_agent='acme_wealth_v3', p=0.3),
        config=[(12, 'routing', 'acme_wealth_v3', 'rr_v0', 'rr_v1', 'wealth agent rollout 30pct of cards and lending traffic')],
        metric=['new_agent'],
        description='New v3 agent acme_wealth_v3 launched day 12, taking 30% of acme_cards_v3/acme_lending_v3 traffic. It performs like its peers (born healthy); the peer agents lose volume but not quality.'),
  ]},
]

# ----------------------------------------------------------------------------------------------
def D(o): return json.dumps(o, separators=(',', ':'))
def pts(s): return dt.datetime.fromisoformat(s)
def fts(d): return d.isoformat()
def shift(s, ms): return fts(pts(s) + dt.timedelta(milliseconds=ms))

def wchoice(rng, weights):
    x = rng.random() * sum(weights.values()); acc = 0
    for k, w in weights.items():
        acc += w
        if x <= acc: return k
    return k

def intensity(inj, day):
    on, du = inj['onset_day'], inj['duration_days']
    if day < on or day > on + du - 1: return 0.0
    if inj.get('shape') == 'ramp':
        return min(1.0, (day - on + 1) / inj['ramp_days'])
    return 1.0

def cohort_match(s, cohort):
    for k, v in cohort.items():
        if k in ('tool', 'tool_name'): continue
        if k == 'segment':
            if s['custom_dims']['segment'] != v: return False
        elif s.get(k) != v: return False
    return True

def new_step(tmpl, step_type, ts, turn_index, **kw):
    r = {k: tmpl[k] for k in PREFIX}
    r['step_type'] = step_type; r['ts'] = ts; r['turn_index'] = turn_index
    r.update(kw)
    return r

def turn_ts(b): return {t['turn_index']: t['ts'] for t in b['turns']}

def add_delay(b, t, ms):
    ms = int(ms)
    if ms <= 0: return
    for r in b['steps']:
        if r['turn_index'] > t or r['step_type'] == 'handoff': r['ts'] = shift(r['ts'], ms)
    for x in b['turns']:
        if x['turn_index'] > t: x['ts'] = shift(x['ts'], ms)
    b['s']['ts_end'] = shift(b['s']['ts_end'], ms)

def truncate(b, k):
    tt = turn_ts(b); last = max(tt)
    b['steps'] = [r for r in b['steps'] if r['step_type'] != 'handoff']
    if k >= last: return
    b['steps'] = [r for r in b['steps'] if r['turn_index'] <= k]
    b['turns'] = [x for x in b['turns'] if x['turn_index'] <= k]
    b['s']['ts_end'] = tt[k + 1]

def flip(b, end, rng, ctx, k=None, ms_keep=None, groups=None):
    s = b['s']
    if k is not None: truncate(b, k)
    else: b['steps'] = [r for r in b['steps'] if r['step_type'] != 'handoff']
    s['session_end'] = end
    s['handoff_by_design'] = False if end == 'handoff' else None
    if end == 'handoff':
        lt = max(r['turn_index'] for r in b['steps'])
        g = wchoice(rng, groups or {'tier1': 1, 'tier2': 1, 'specialist': 1})
        b['steps'].append(new_step(b['steps'][0], 'handoff', s['ts_end'], lt, outcome='ok', error_class=None,
                                   duration_ms=int(rng.lognormvariate(math.log(1300), 0.4)), handoff_by_design=False, handoff_group=g))
    ms = s['milestones_reached']
    n = len(ms) - 1 if ms_keep is None else ms_keep
    s['milestones_reached'] = ms[:max(1, min(n, len(ms)))]
    s['quality_score'] = rng.choice(ctx['qpool'][(s['tenant'], s['judge_version'])])
    if s['csat'] is not None: s['csat'] = rng.choice(ctx['cpool'][s['tenant']])
    ctx['flips'][end] += 1

def finalize(b, recount_kb=True):
    s = b['s']; st = b['steps']
    for i, r in enumerate(st, 1): r['step_seq'] = i
    s['tool_error_count'] = sum(1 for r in st if r['step_type'] == 'tool_call' and r['outcome'] != 'ok')
    if recount_kb and not b.get('no_kb_recount'):
        s['kb_miss_count'] = sum(1 for r in st if r['step_type'] == 'kb_lookup' and not r['kb_hit'])
    s['guardrail_blocks'] = sum(1 for r in st if r['step_type'] == 'guardrail' and r['outcome'] == 'blocked')
    okc = sum(r['cost_usd'] for r in st if r['step_type'] == 'llm_call' and r['outcome'] == 'ok')
    s['cost_usd'] = round(b['cost0_s'] + okc - b['cost0_steps'], 6)
    s['turns'] = max(r['turn_index'] for r in st)
    if s['ts_end'] != b['ts_end0']:
        s['duration_s'] = int((pts(s['ts_end']) - pts(s['ts_start'])).total_seconds())

# ---------------------------------------------------------------- novel handlers
def h_tool_errors(b, rng, I, P, ctx):
    s = b['s']; new = 0
    for r in list(b['steps']):
        if r['step_type'] == 'tool_call' and r['tool_name'] == P['tool'] and r['outcome'] == 'ok' and rng.random() < P['p'] * I:
            kind = wchoice(rng, P['mix']); old = r['duration_ms']
            if kind == '5xx':
                r.update(outcome='error', error_class='upstream.platform_5xx', status_code=503); r['duration_ms'] = int(old * rng.uniform(1.0, 3.0))
            elif kind == 'timeout':
                r.update(outcome='timeout', error_class='upstream.timeout', status_code=0); r['duration_ms'] = int(rng.uniform(5000, 12000))
            else:
                r.update(outcome='error', error_class='upstream.client_4xx', status_code=422); r['duration_ms'] = int(old * rng.uniform(0.5, 1.0))
            r['response_bytes'] = 0; r['result_field_count'] = 0
            add_delay(b, r['turn_index'], r['duration_ms'] - old)
            new += 1
    if new and s['session_end'] == 'resolved' and rng.random() < P['flip_p']:
        flip(b, 'handoff' if rng.random() < P['handoff_share'] else 'abandoned', rng, ctx)
    return new > 0

def h_tool_latency(b, rng, I, P, ctx):
    s = b['s']; hit = None
    fe = 1 + (P['factor'] - 1) * I
    for r in list(b['steps']):
        if r['step_type'] == 'tool_call' and r['tool_name'] == P['tool']:
            old = r['duration_ms']; r['duration_ms'] = int(old * fe * rng.lognormvariate(0, 0.2))
            add_delay(b, r['turn_index'], r['duration_ms'] - old)
            hit = hit or r['turn_index']
    if hit and s['session_end'] == 'resolved' and rng.random() < P['flip_p'] * I:
        flip(b, 'abandoned', rng, ctx, k=hit)
    return bool(hit)

def h_guardrail(b, rng, I, P, ctx):
    s = b['s']
    if rng.random() >= P['p'] * I: return False
    t = rng.randint(1, min(s['turns'], 3))
    idx = max(i for i, r in enumerate(b['steps']) if r['turn_index'] == t and r['step_type'] != 'handoff')
    ts = turn_ts(b)[t]
    b['steps'].insert(idx + 1, new_step(b['steps'][0], 'guardrail', ts, t, outcome='blocked', error_class='guardrail.blocked',
                                        duration_ms=rng.randint(5, 25), guardrail_name=wchoice(rng, P['names'])))
    if s['session_end'] == 'resolved' and rng.random() < P['flip_p']:
        flip(b, 'abandoned' if rng.random() < 0.5 else 'handoff', rng, ctx, k=min(s['turns'], t + rng.randint(0, 1)))
    return True

def h_llm_latency(b, rng, I, P, ctx):
    s = b['s']; fe = 1 + (P['factor'] - 1) * I
    for r in list(b['steps']):
        if r['step_type'] == 'llm_call':
            old = r['duration_ms']; r['duration_ms'] = int(old * fe * rng.lognormvariate(0, 0.1))
            add_delay(b, r['turn_index'], r['duration_ms'] - old)
    if s['session_end'] == 'resolved' and rng.random() < P['flip_p'] * I:
        flip(b, 'abandoned', rng, ctx, k=rng.randint(max(1, s['turns'] // 2), s['turns']))
    return True

def h_channel_abandon(b, rng, I, P, ctx):
    s = b['s']
    if s['session_end'] != 'resolved' or rng.random() >= P['p'] * I: return False
    k = rng.randint(1, max(1, s['turns'] - 1))
    flip(b, 'abandoned', rng, ctx, k=k, ms_keep=min(len(s['milestones_reached']) - 1, k))
    return True

def h_unplanned_handoff(b, rng, I, P, ctx):
    s = b['s']
    if s['session_end'] != 'resolved' or rng.random() >= P['p'] * I: return False
    k = rng.randint(1, min(P['max_k'], s['turns']))
    flip(b, 'handoff', rng, ctx, k=k, ms_keep=min(len(s['milestones_reached']) - 1, k), groups=P['groups'])
    return True

def h_funnel_stall(b, rng, I, P, ctx):
    s = b['s']
    if s['session_end'] != 'resolved' or rng.random() >= P['p'] * I: return False
    ms = s['milestones_reached']
    if P['stage'] not in ms: return False
    b['steps'] = [r for r in b['steps'] if not (r['step_type'] == 'tool_call' and r['tool_name'] == P['tool'])]
    flip(b, 'abandoned' if rng.random() < P['abandon_share'] else 'handoff', rng, ctx, ms_keep=ms.index(P['stage']) + 1)
    return True

def h_retry_storm(b, rng, I, P, ctx):
    s = b['s']; n = 0; out = []
    for r in b['steps']:
        out.append(r)
        if r['step_type'] == 'llm_call' and r['outcome'] == 'ok' and r['retry_count'] == 0 and rng.random() < P['p'] * I:
            x = dict(r); x['retry_count'] = 1; x['retry_reason'] = P['reason']
            x['output_tokens'] = max(20, int(r['output_tokens'] * rng.uniform(0.8, 1.2)))
            x['cost_usd'] = round(x['input_tokens'] * 3e-6 + x['output_tokens'] * 15e-6, 6)
            x['duration_ms'] = int(r['duration_ms'] * rng.uniform(0.8, 1.3))
            out.append(x); n += 1
    if not n: return False
    b['steps'] = out
    for x in [r for r in out if r.get('retry_reason') == P['reason']]:
        add_delay(b, x['turn_index'], x['duration_ms'])
    if s['session_end'] == 'resolved' and rng.random() < P['flip_p'] * n:
        flip(b, 'abandoned', rng, ctx)
    return True

def h_provider_errors(b, rng, I, P, ctx):
    s = b['s']; fe = 1 + (P['lat_factor'] - 1) * I; out = []; n = 0
    for r in b['steps']:
        if r['step_type'] == 'llm_call':
            old = r['duration_ms']; r['duration_ms'] = int(old * fe * rng.lognormvariate(0, 0.1))
            add_delay(b, r['turn_index'], r['duration_ms'] - old)
            if r['outcome'] == 'ok' and r['retry_count'] == 0 and rng.random() < P['p'] * I:
                e = dict(r); e['outcome'] = 'error'; e['error_class'] = 'model.provider_error'
                e['duration_ms'] = int(rng.uniform(300, 6000))
                out.append(e); r['retry_count'] = 1; r['retry_reason'] = 'provider_error'; n += 1
                add_delay(b, r['turn_index'], e['duration_ms'])
        out.append(r)
    b['steps'] = out
    if n and s['session_end'] == 'resolved' and rng.random() < P['flip_p']:
        flip(b, 'handoff' if rng.random() < 0.5 else 'abandoned', rng, ctx)
    return True

def h_context_overflow(b, rng, I, P, ctx):
    s = b['s']
    if s['session_end'] != 'resolved' or s['turns'] < P['min_turn'] or rng.random() >= P['p'] * I: return False
    t = rng.randint(P['min_turn'], s['turns'])
    r = next(r for r in b['steps'] if r['step_type'] == 'llm_call' and r['turn_index'] == t)
    r['outcome'] = 'error'; r['error_class'] = 'model.context_overflow'
    r['input_tokens'] = rng.randint(200001, 215000); r['output_tokens'] = 0
    r['cost_usd'] = round(r['input_tokens'] * 3e-6, 6); r['duration_ms'] = int(rng.uniform(150, 700))
    flip(b, 'handoff' if rng.random() < P['handoff_share'] else 'abandoned', rng, ctx, k=t)
    return True

HANDLERS = dict(tool_errors=h_tool_errors, tool_latency=h_tool_latency, guardrail=h_guardrail, llm_latency=h_llm_latency,
                channel_abandon=h_channel_abandon, unplanned_handoff=h_unplanned_handoff, funnel_stall=h_funnel_stall,
                retry_storm=h_retry_storm, provider_errors=h_provider_errors, context_overflow=h_context_overflow)

# ----------------------------------------------------------------------------------------------
def read_lines(path):
    with open(path, newline='') as f: txt = f.read()
    nl = '\r\n' if '\r\n' in txt else '\n'
    return [l for l in txt.split(nl) if l != ''], nl

def build(spec):
    src, gt_rel, label = SRC[spec['source']]
    out = BENCH + '/' + spec['corpus']
    if os.path.exists(out): shutil.rmtree(out)
    os.makedirs(out + '/corpus')
    shutil.copytree(src + '/labels', out + '/labels')
    shutil.copy(src + '/asks.md', out + '/asks.md')
    shutil.copy(src + '/' + gt_rel, out + '/planted_ground_truth.json')
    seed = spec['seed']
    log = {'corpus': spec['corpus'], 'ops': {}}

    sessions = [json.loads(l) for l in gzip.open(src + '/corpus/sessions.jsonl.gz', 'rt')]
    S = {s['session_id']: s for s in sessions}
    labelled = set()
    for fn in os.listdir(src + '/labels'):
        for l in open(src + '/labels/' + fn):
            if l.strip(): labelled.add(json.loads(l)['session_id'])
    ctx = {'qpool': collections.defaultdict(list), 'cpool': collections.defaultdict(list), 'flips': collections.Counter()}
    for s in sessions:
        if s['session_end'] != 'resolved':
            ctx['qpool'][(s['tenant'], s['judge_version'])].append(s['quality_score'])
            if s['csat'] is not None: ctx['cpool'][s['tenant']].append(s['csat'])

    touched = set(); removed = set(); reassigned = {}; clone_plan = []; drop_ops = []
    new_config = []; catalog_agents = []
    # ---- pass-1 benign decisions that change session identity/volume
    for bn in spec['benign']:
        rng = random.Random(f"{seed}:{bn['id']}"); P = bn['params']; h = bn['handler']
        if h == 'holiday':
            days = range(bn['onset_day'], bn['onset_day'] + bn['duration_days'])
            for s in sessions:
                if s['day'] in days and s['session_id'] not in labelled and rng.random() < P['p']:
                    removed.add(s['session_id'])
        elif h == 'reassign':
            for s in sessions:
                if s['tenant'] == bn['tenant'] and s['agent_id'] in P['src_agents'] and s['day'] >= bn['onset_day'] and rng.random() < P['p']:
                    s['agent_id'] = P['new_agent']; reassigned[s['session_id']] = P['new_agent']; touched.add(s['session_id'])
            catalog_agents.append((bn['tenant'], P['new_agent']))
        elif h == 'clone_channel':
            for d in range(bn['onset_day'], bn['onset_day'] + bn['duration_days']):
                pool = [s for s in sessions if s['tenant'] == bn['tenant'] and s['channel'] == P['channel'] and s['day'] == d]
                pool.sort(key=lambda s: s['session_id'])
                for _ in range(round(len(pool) * P['extra_ratio'])):
                    clone_plan.append(rng.choice(pool)['session_id'])
            touched.update(clone_plan)
        elif h == 'drop_step_type':
            tg = [s['session_id'] for s in sessions if s['tenant'] == bn['tenant'] and s['agent_id'] == P['agent'] and s['day'] >= bn['onset_day']]
            drop_ops.append((bn, tg)); touched.update(tg)
        for c in bn.get('config', []): new_config.append(c)
        log['ops'][bn['id']] = {'removed': len(removed), 'reassigned': len(reassigned), 'clones': len(clone_plan)}

    # ---- targets for novel faults and version ops
    for nf in spec['novel']:
        nf['_targets'] = sorted(s['session_id'] for s in sessions
                                if s['session_id'] not in removed and s['session_id'] not in labelled and s['tenant'] == nf['tenant']
                                and intensity(nf, s['day']) > 0 and cohort_match(s, nf['cohort']))
        touched.update(nf['_targets'])
        for v in nf['versions']:
            v['_targets'] = sorted(s['session_id'] for s in sessions if s['session_id'] not in removed and s['tenant'] == nf['tenant']
                                   and v['from_day'] <= s['day'] <= v['to_day']
                                   and ((('agent' in v) and s['agent_id'] == v['agent']) or (('intent' in v) and s['intent'] == v['intent'])))
            touched.update(v['_targets'])
    touched -= removed

    # ---- load bundles
    B = {sid: {'s': S[sid], 'steps': [], 'turns': []} for sid in touched}
    with gzip.open(src + '/corpus/agent_steps.jsonl.gz', 'rt') as f:
        for l in f:
            sid = l[15:28]
            if sid in B: B[sid]['steps'].append(json.loads(l))
    with gzip.open(src + '/corpus/turns.jsonl.gz', 'rt') as f:
        for l in f:
            sid = l[15:28]
            if sid in B: B[sid]['turns'].append(json.loads(l))
    durmis = 0
    for sid, b in B.items():
        assert b['steps'] and b['turns'], sid
        b['cost0_s'] = b['s']['cost_usd']; b['ts_end0'] = b['s']['ts_end']
        b['cost0_steps'] = sum(r['cost_usd'] for r in b['steps'] if r['step_type'] == 'llm_call' and r['outcome'] == 'ok')
        if int((pts(b['s']['ts_end']) - pts(b['s']['ts_start'])).total_seconds()) != b['s']['duration_s']: durmis += 1
        if sid in reassigned:
            for r in b['steps']: r['agent_id'] = reassigned[sid]
    log['duration_floor_mismatch_in_touched'] = durmis
    clone_src = {sid: json.loads(json.dumps(B[sid])) for sid in set(clone_plan)}

    dirty = set(sid for sid in reassigned)
    # ---- versions + config rows
    for nf in spec['novel']:
        for c in nf['config']:
            day, kind, target, frm, to, note = c
            if frm == 'AUTO':
                v = next(v for v in nf['versions'] if v['from_day'] == day)
                if v['field'] == 'tool_version':
                    vals = collections.Counter(r['tool_version'] for sid in v['_targets'] for r in B[sid]['steps']
                                               if r['step_type'] == 'tool_call' and r['tool_name'] == v['tool'])
                else:
                    vals = collections.Counter(B[sid]['s'][v['field']] for sid in v['_targets'])
                frm = vals.most_common(1)[0][0]
                assert frm != to, (nf['id'], frm)
            new_config.append((day, kind, target, frm, to, note))
        for v in nf['versions']:
            for sid in v['_targets']:
                b = B[sid]
                if v['field'] == 'tool_version':
                    for r in b['steps']:
                        if r['step_type'] == 'tool_call' and r['tool_name'] == v['tool']: r['tool_version'] = v['value']
                else:
                    b['s'][v['field']] = v['value']
                    for r in b['steps']: r[v['field']] = v['value']
                dirty.add(sid)
    # ---- novel faults
    for nf in spec['novel']:
        rng = random.Random(f"{seed}:{nf['id']}"); h = HANDLERS[nf['handler']]; hits = 0
        ctx['flips'] = collections.Counter()
        for sid in nf['_targets']:
            b = B[sid]
            if h(b, rng, intensity(nf, b['s']['day']), nf['params'], ctx): hits += 1
            dirty.add(sid)
        log['ops'][nf['id']] = {'targets': len(nf['_targets']), 'hits': hits, 'flips': dict(ctx['flips'])}
    for sid in dirty: finalize(B[sid])
    # ---- instrumentation drop (last)
    for bn, tg in drop_ops:
        n = 0
        for sid in tg:
            b = B[sid]; finalize(b)
            before = len(b['steps'])
            b['steps'] = [r for r in b['steps'] if r['step_type'] != bn['params']['step_type']]
            n += before - len(b['steps'])
            for i, r in enumerate(b['steps'], 1): r['step_seq'] = i
            b['no_kb_recount'] = True; dirty.add(sid)
        log['ops'][bn['id']]['rows_dropped'] = n
    # ---- clones
    clones = []
    if clone_plan:
        crng = random.Random(f"{seed}:clones")
        nxt = max(int(sid[-6:]) for sid in S) + 1
        for srcid in clone_plan:
            c = json.loads(json.dumps(clone_src[srcid]))
            s = c['s']; tenant_prefix = srcid[:7]
            nid = f"{tenant_prefix}{nxt:06d}"; nxt += 1
            start = pts(s['ts_start'])
            delta = crng.randint(-3 * 3600, 3 * 3600)
            if (start + dt.timedelta(seconds=delta)).date() != start.date(): delta = -delta
            if (start + dt.timedelta(seconds=delta)).date() != start.date(): delta = 0
            ms = delta * 1000
            s['session_id'] = nid; s['ts_start'] = shift(s['ts_start'], ms); s['ts_end'] = shift(s['ts_end'], ms)
            s['csat'] = None; s['custom_dims'] = dict(s['custom_dims']); s['custom_dims']['customer_ref'] = 'c_%08x' % crng.getrandbits(32)
            for r in c['steps']: r['session_id'] = nid; r['ts'] = shift(r['ts'], ms)
            for t in c['turns']: t['session_id'] = nid; t['ts'] = shift(t['ts'], ms)
            clones.append(c)
    # ---- write sessions
    counts = collections.Counter(); stc = collections.Counter()
    with gzip.open(out + '/corpus/sessions.jsonl.gz', 'wt', compresslevel=6, newline='\n') as f:
        for s in sessions:
            if s['session_id'] in removed: continue
            f.write(D(s) + '\n'); counts['sessions'] += 1
        for c in clones:
            f.write(D(c['s']) + '\n'); counts['sessions'] += 1
    written = set()
    for fname, key in (('agent_steps', 'steps'), ('turns', 'turns')):
        with gzip.open(src + f'/corpus/{fname}.jsonl.gz', 'rt') as fi, gzip.open(out + f'/corpus/{fname}.jsonl.gz', 'wt', compresslevel=6, newline='\n') as fo:
            for l in fi:
                sid = l[15:28]
                if sid in removed: continue
                if sid in dirty:
                    if (fname, sid) in written: continue
                    written.add((fname, sid))
                    for r in B[sid][key]:
                        fo.write(D(r) + '\n'); counts[fname] += 1
                        if key == 'steps': stc[r['step_type']] += 1
                    continue
                fo.write(l); counts[fname] += 1
                if key == 'steps':
                    i = l.index('"step_type":"') + 13; stc[l[i:l.index('"', i)]] += 1
            for c in clones:
                for r in c[key]:
                    fo.write(D(r) + '\n'); counts[fname] += 1
                    if key == 'steps': stc[r['step_type']] += 1
    # ---- feedback
    lines, nl = read_lines(src + '/corpus/feedback.csv')
    fb = [lines[0]]
    for l in lines[1:]:
        sid, tenant, day, csat = l.split(',')
        if sid in removed: continue
        if sid in B and B[sid]['s']['csat'] is not None: csat = str(B[sid]['s']['csat'])
        fb.append(','.join([sid, tenant, day, csat]))
    open(out + '/corpus/feedback.csv', 'w', newline='').write(nl.join(fb) + nl)
    counts['csat_responses'] = len(fb) - 1
    # ---- config timeline
    lines, nl = read_lines(src + '/corpus/config_timeline.csv')
    rows = [(int(l.split(',')[0]), i, l) for i, l in enumerate(lines[1:])]
    for j, (day, kind, target, frm, to, note) in enumerate(new_config):
        tenant = next(x['tenant'] for x in spec['novel'] + spec['benign'] if any(c[0] == day and c[2] == target for c in x.get('config', [])))
        date = (EPOCH + dt.timedelta(days=day)).date().isoformat()
        rows.append((day, 1000 + j, ','.join([str(day), date, tenant, kind, target, frm, to, note])))
    rows.sort()
    open(out + '/corpus/config_timeline.csv', 'w', newline='').write(nl.join([lines[0]] + [r[2] for r in rows]) + nl)
    counts['config_changes'] = len(rows)
    # ---- manifest, catalog
    man = json.load(open(src + '/manifest.json'))
    man['rows']['sessions'] = counts['sessions']; man['rows']['agent_steps'] = counts['agent_steps']
    man['rows']['turns'] = counts['turns']; man['rows']['config_changes'] = counts['config_changes']
    man['rows']['csat_responses'] = counts['csat_responses']
    man['step_type_counts'] = {k: stc[k] for k in man['step_type_counts']} | {k: v for k, v in stc.items() if k not in man['step_type_counts']}
    man['benchmark_corpus'] = spec['corpus']
    json.dump(man, open(out + '/manifest.json', 'w'), indent=2)
    cat = json.load(open(src + '/catalog.json'))
    for tenant, agent in catalog_agents:
        if agent not in cat['tenants'][tenant]['agents']: cat['tenants'][tenant]['agents'].append(agent)
    json.dump(cat, open(out + '/catalog.json', 'w'), indent=2)
    log['counts'] = dict(counts); log['config_added'] = new_config
    os.makedirs(BENCH + '/_build', exist_ok=True)
    json.dump(log, open(BENCH + f"/_build/{spec['corpus']}_log.json", 'w'), indent=1)
    print(json.dumps(log, indent=1))

if __name__ == '__main__':
    want = sys.argv[1:]
    for spec in SPECS:
        if not want or spec['corpus'] in want: build(spec)
