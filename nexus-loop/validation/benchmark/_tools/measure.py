#!/usr/bin/env python
"""Measure every injection from the FINAL written corpus and write answer_key.json."""
import json, gzip, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import SPECS, SRC, BENCH, cohort_match

def r4(x): return None if x is None else round(x, 4)

def build_key(spec):
    cdir = BENCH + '/' + spec['corpus']
    sessions = [json.loads(l) for l in gzip.open(cdir + '/corpus/sessions.jsonl.gz', 'rt')]
    tool = collections.defaultdict(lambda: [0, 0, 0]); llm = collections.defaultdict(lambda: [0, 0, 0, 0])
    stype = collections.Counter()
    with gzip.open(cdir + '/corpus/agent_steps.jsonl.gz', 'rt') as f:
        for l in f:
            r = json.loads(l); t = r['step_type']
            if t == 'tool_call':
                a = tool[(r['tenant'], r['tool_name'], r['day'])]; a[0] += 1; a[1] += r['outcome'] != 'ok'; a[2] += r['duration_ms']
            elif t == 'llm_call':
                a = llm[(r['tenant'], r['agent_id'], r['day'])]; a[0] += 1; a[1] += r['outcome'] != 'ok'; a[2] += r['retry_count'] > 0; a[3] += r['duration_ms']
            stype[(r['tenant'], r['agent_id'], t, r['day'])] += 1

    def days(a, b): return range(max(0, a), min(55, b) + 1)
    def sess(tenant, cohort, dd): return [s for s in sessions if (tenant == '*' or s['tenant'] == tenant) and s['day'] in dd and cohort_match(s, cohort)]
    def share(ss, pred): return (sum(1 for s in ss if pred(s)) / len(ss)) if ss else None
    def agg(tab, key3, dd, num, den=0):
        n = sum(tab[key3 + (d,)][den] for d in dd if key3 + (d,) in tab); k = sum(tab[key3 + (d,)][num] for d in dd if key3 + (d,) in tab)
        return k / n if n else None

    def metric(m, inj, dd):
        t, c = inj['tenant'], inj['cohort']
        kind = m[0]
        if kind == 'tool_error_rate': return agg(tool, (t, m[1]), dd, 1)
        if kind == 'tool_latency_mean': return agg(tool, (t, m[1]), dd, 2)
        if kind == 'llm_latency_mean': return agg(llm, (t, m[1]), dd, 3)
        if kind == 'llm_retry_share': return agg(llm, (t, m[1]), dd, 2)
        if kind == 'llm_error_rate': return agg(llm, (t, m[1]), dd, 1)
        ss = sess(t, c, dd)
        if kind == 'guardrail_session_share': return share(ss, lambda s: s['guardrail_blocks'] > 0)
        if kind == 'abandon_rate': return share(ss, lambda s: s['session_end'] == 'abandoned')
        if kind == 'unplanned_handoff_rate': return share(ss, lambda s: s['session_end'] == 'handoff' and not s['handoff_by_design'])
        if kind == 'resolution_rate': return share(ss, lambda s: s['session_end'] == 'resolved')
        if kind == 'milestone_reach_rate': return share(ss, lambda s: m[1] in s['milestones_reached'])
        if kind == 'volume': return len(sess('*', {}, dd)) / len(dd)
        if kind == 'steps_per_session':
            n = len(sess(t, {'agent_id': m[1]}, dd)); k = sum(stype[(t, m[1], m[2], d)] for d in dd)
            return k / n if n else None
        if kind == 'channel_share':
            allss = sess(t, {}, dd); return share(allss, lambda s: s['channel'] == m[1])
        raise ValueError(kind)

    src_label = SRC[spec['source']][2]
    gt = json.load(open(cdir + '/planted_ground_truth.json'))
    key = {'corpus': spec['corpus'], 'split': spec['split'], 'source': src_label, 'seed': spec['seed'],
           'magnitude_tier_rule': 'tier refers to the primary metric: subtle ~5-12% relative (or +2-5 pts on a small-base rate), medium ~15-35% relative (or +6-12 pts), large >=50% relative (or >=15 pts)',
           'novel_faults': [], 'benign_events': [], 'planted_faults': gt['faults'], 'planted_decoys': gt['decoys']}
    report = []
    for nf in spec['novel']:
        on, du = nf['onset_day'], nf['duration_days']
        bd, dd = days(on - 14, on - 1), days(on, on + du - 1)
        before, during = metric(nf['metric'], nf, bd), metric(nf['metric'], nf, dd)
        rb, rd = metric(['resolution_rate'], nf, bd), metric(['resolution_rate'], nf, dd)
        extra = {}
        if nf['id'] == 'N1' and nf['type'] == 'context_overflow':
            extra = {'llm_error_rate_before': r4(metric(['llm_error_rate', 'acme_cards_v3'], nf, bd)), 'llm_error_rate_during': r4(metric(['llm_error_rate', 'acme_cards_v3'], nf, dd))}
        if nf['shape'] == 'ramp':
            pk = days(on + nf['ramp_days'] - 1, on + du - 1)
            extra['primary_at_full_ramp'] = r4(metric(nf['metric'], nf, pk))
        rel = (during - before) / before if before else None
        ent = {k: nf[k] for k in ('id', 'type', 'tenant', 'cohort', 'onset_day', 'duration_days', 'shape')}
        if nf['shape'] == 'ramp': ent['ramp_days'] = nf['ramp_days']
        ent.update(magnitude_tier=nf['magnitude_tier'], primary_metric=nf['primary_metric'],
                   measured=dict(before=r4(before), during=r4(during), relative_change=r4(rel), abs_change=r4(during - before),
                                 resolution_before=r4(rb), resolution_during=r4(rd), windows={'before': [bd[0], bd[-1]], 'during': [dd[0], dd[-1]]}, **extra),
                   has_config_row=any(c[0] == on for c in nf['config']),
                   accepted_cause_classes=nf['accepted_cause_classes'], description=nf['description'])
        key['novel_faults'].append(ent)
        report.append((spec['corpus'], nf['id'], nf['type'], nf['magnitude_tier'], r4(before), r4(during), r4(rel), r4(rb), r4(rd), extra))
    for bn in spec['benign']:
        on, du = bn['onset_day'], bn['duration_days']
        bd, dd = days(on - 14, on - 1), days(on, on + du - 1)
        meas = {}
        if bn['metric'][0] == 'new_agent':
            t = bn['tenant']; new = bn['params']['new_agent']
            meas = {'new_agent_sessions_per_day': round(len(sess(t, {'agent_id': new}, dd)) / len(dd), 1),
                    'new_agent_resolution': r4(metric(['resolution_rate'], {'tenant': t, 'cohort': {'agent_id': new}}, dd)),
                    'peer_resolution_same_window': {a: r4(metric(['resolution_rate'], {'tenant': t, 'cohort': {'agent_id': a}}, dd)) for a in bn['params']['src_agents']},
                    'peer_sessions_per_day_before': {a: round(len(sess(t, {'agent_id': a}, bd)) / len(bd), 1) for a in bn['params']['src_agents']},
                    'peer_sessions_per_day_during': {a: round(len(sess(t, {'agent_id': a}, dd)) / len(dd), 1) for a in bn['params']['src_agents']}}
        else:
            meas = {'before': r4(metric(bn['metric'], bn, bd)), 'during': r4(metric(bn['metric'], bn, dd))}
            if bn['metric'][0] == 'volume':
                meas['resolution_before'] = r4(metric(['resolution_rate'], {'tenant': '*', 'cohort': {}}, bd))
                meas['resolution_during'] = r4(metric(['resolution_rate'], {'tenant': '*', 'cohort': {}}, dd))
            elif bn['metric'][0] == 'channel_share':
                c = {'tenant': bn['tenant'], 'cohort': bn['cohort']}
                meas['channel_resolution_before'] = r4(metric(['resolution_rate'], c, bd)); meas['channel_resolution_during'] = r4(metric(['resolution_rate'], c, dd))
                meas['channel_abandon_before'] = r4(metric(['abandon_rate'], c, bd)); meas['channel_abandon_during'] = r4(metric(['abandon_rate'], c, dd))
            else:
                c = {'tenant': bn['tenant'], 'cohort': bn['cohort']}
                meas['resolution_before'] = r4(metric(['resolution_rate'], c, bd)); meas['resolution_during'] = r4(metric(['resolution_rate'], c, dd))
        meas['metric'] = bn['metric']
        ent = {k: bn[k] for k in ('id', 'type', 'tenant', 'cohort', 'onset_day', 'duration_days', 'description')}
        ent['measured'] = meas; ent['correct_reading'] = 'not a regression'
        key['benign_events'].append(ent)
        report.append((spec['corpus'], bn['id'], bn['type'], 'benign', meas))
    json.dump(key, open(cdir + '/answer_key.json', 'w'), indent=1)
    for r in report: print(r)

if __name__ == '__main__':
    want = sys.argv[1:]
    for spec in SPECS:
        if not want or spec['corpus'] in want: build_key(spec)
