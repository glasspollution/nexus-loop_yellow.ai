#!/usr/bin/env python
"""Blind benchmark evaluator (stdlib only).

usage: python evaluate.py --bench-dir <bench>/bench-01 --incidents incidents.json [--json]

incidents.json:
{"incidents": [
  {"id": "i1", "tenant": "acme-bank", "cohort": {"intent": "card_block"}, "from_day": 15, "to_day": 26,
   "is_regression": true, "cause_class": "tool.outage", "metrics": ["tool_call.fail"]}
]}
cohort may be {} (tenant-wide); tenant may be "*" (cross-tenant). Cohort keys: intent, agent_id, channel, tool, segment.
"""
import argparse, json, os, sys
from collections import defaultdict

TOL_BEFORE = 3


def norm_cohort(c):
    out = {}
    for k, v in (c or {}).items():
        out['tool' if k == 'tool_name' else k] = v
    return out


def window_ok(inc, onset, duration):
    return not (inc['to_day'] < onset - TOL_BEFORE or inc['from_day'] > onset + duration)


def tenant_ok_fault(inc, fault_tenant):
    return fault_tenant == '*' or inc.get('tenant') == fault_tenant


def cohort_ok(inc_c, fault_c):
    # empty fault cohort matches any incident cohort; a tenant-wide incident (empty cohort)
    # matches any fault on that tenant and is scored as tenant-level localisation.
    if not fault_c or not inc_c:
        return True
    return any(k in fault_c and fault_c[k] == v for k, v in inc_c.items())


def exact_local(inc_c, fault_c):
    return bool(fault_c) and any(k in fault_c and fault_c[k] == v for k, v in inc_c.items())


def match_fault(inc, f):
    return (tenant_ok_fault(inc, f['tenant']) and cohort_ok(norm_cohort(inc.get('cohort')), norm_cohort(f.get('cohort')))
            and window_ok(inc, f['onset_day'], f['duration_days']))


def match_benign(inc, e):
    ic, ec = norm_cohort(inc.get('cohort')), norm_cohort(e.get('cohort'))
    if e['tenant'] == '*':
        if ic and not any(k in ec for k in ic):
            return False
    else:
        if inc.get('tenant') not in (e['tenant'], '*'):
            return False
        if ic and ec and not any(k in ec and ec[k] == v for k, v in ic.items()):
            return False
    return window_ok(inc, e['onset_day'], e['duration_days'])


def match_decoy(inc, d):
    t = inc.get('tenant')
    tenant_ok = d['tenant'] == '*' or t == '*' or t == d['tenant']
    return tenant_ok and window_ok(inc, d['onset_day'], d['duration_days'])


def cohort_dim(c):
    keys = sorted(k for k in norm_cohort(c) if k != 'intent') or sorted(norm_cohort(c))
    return keys[0] if keys else 'tenant'


def score_faults(faults, regs, novel=True):
    rows = []
    for f in faults:
        hits = [i for i in regs if match_fault(i, f)]
        fc = norm_cohort(f.get('cohort'))
        row = {'id': f['id'], 'type': f.get('type', f.get('cause_class')), 'tenant': f['tenant'], 'cohort': f.get('cohort', {}),
               'onset_day': f['onset_day'], 'duration_days': f['duration_days'], 'hit': bool(hits),
               'magnitude_tier': f.get('magnitude_tier', 'planted'), 'shape': f.get('shape', 'step'),
               'dimension': cohort_dim(f.get('cohort', {})), 'has_config_row': f.get('has_config_row', True),
               'matched_incidents': [i.get('id') for i in hits]}
        accepted = f.get('accepted_cause_classes') or ([f['cause_class']] if f.get('cause_class') else [])
        if hits:
            first = min(hits, key=lambda i: i['from_day'])
            row['lag_days'] = max(0, first['from_day'] - f['onset_day'])
            row['localisation'] = 'exact' if any(exact_local(norm_cohort(i.get('cohort')), fc) for i in hits) else 'tenant_level'
            row['cause_correct'] = any(i.get('cause_class') in accepted for i in hits)
        else:
            row.update(lag_days=None, localisation=None, cause_correct=False)
        row['accepted_cause_classes'] = accepted
        rows.append(row)
    return rows


def breakdown(rows, key):
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        agg[str(r[key])][1] += 1
        agg[str(r[key])][0] += int(r['hit'])
    return {k: {'hit': v[0], 'total': v[1], 'recall': round(v[0] / v[1], 3)} for k, v in sorted(agg.items())}


def evaluate(bench_dir, incidents_path):
    key = json.load(open(os.path.join(bench_dir, 'answer_key.json')))
    raw = json.load(open(incidents_path))
    incs = raw['incidents'] if isinstance(raw, dict) else raw
    for n, i in enumerate(incs):
        i.setdefault('id', f'inc{n}')
        i['from_day'] = int(i['from_day']); i['to_day'] = int(i['to_day'])
    regs = [i for i in incs if i.get('is_regression') is True]
    dismiss = [i for i in incs if i.get('is_regression') is False]
    novel = score_faults(key['novel_faults'], regs)
    planted = score_faults(key.get('planted_faults', []), regs, novel=False)

    benign = []
    for e in key.get('benign_events', []):
        bad = [i for i in regs if match_benign(i, e)]
        ok = [i for i in dismiss if match_benign(i, e)]
        benign.append({'id': e['id'], 'type': e['type'], 'tenant': e['tenant'], 'result': 'FAIL' if bad else 'PASS',
                       'examined': bool(ok), 'offending_incidents': [i['id'] for i in bad]})

    all_faults = key['novel_faults'] + key.get('planted_faults', [])
    decoys = []
    for d in key.get('planted_decoys', []):
        fa = [i for i in regs if match_decoy(i, d) and not any(match_fault(i, f) for f in all_faults)]
        cl = [i for i in dismiss if match_decoy(i, d)]
        res = 'FALSE_ALARM' if fa else ('CLEAN' if cl else 'QUIET')
        decoys.append({'id': d['id'], 'kind': d.get('kind'), 'tenant': d['tenant'], 'result': res, 'offending_incidents': [i['id'] for i in fa]})

    fps, tp = [], 0
    for i in regs:
        mf = any(match_fault(i, f) for f in all_faults)
        tp += int(mf)
        if mf or any(match_benign(i, e) for e in key.get('benign_events', [])) or any(match_decoy(i, d) for d in key.get('planted_decoys', [])):
            continue
        fps.append({k: i.get(k) for k in ('id', 'tenant', 'cohort', 'from_day', 'to_day', 'cause_class')})

    def summ(rows):
        h = sum(r['hit'] for r in rows)
        return {'hit': h, 'total': len(rows), 'recall': round(h / len(rows), 3) if rows else None,
                'exact_localisation': sum(1 for r in rows if r['localisation'] == 'exact'),
                'cause_correct': sum(1 for r in rows if r['cause_correct']),
                'mean_lag_days': round(sum(r['lag_days'] for r in rows if r['hit']) / h, 2) if h else None}

    return {
        'corpus': key['corpus'], 'split': key['split'], 'n_incidents': len(incs), 'n_regression_incidents': len(regs),
        'novel': {'summary': summ(novel), 'by_magnitude_tier': breakdown(novel, 'magnitude_tier'), 'by_shape': breakdown(novel, 'shape'),
                  'by_dimension': breakdown(novel, 'dimension'), 'by_has_config_row': breakdown(novel, 'has_config_row'), 'faults': novel},
        'planted': {'summary': summ(planted), 'faults': planted},
        'benign': {'pass': sum(1 for b in benign if b['result'] == 'PASS'), 'total': len(benign), 'events': benign},
        'decoys': {'false_alarms': sum(1 for d in decoys if d['result'] == 'FALSE_ALARM'), 'events': decoys},
        'false_positives': fps,
        'precision': round(tp / len(regs), 3) if regs else None,
    }


def render(r):
    L = []
    L.append(f"== {r['corpus']} ({r['split']}) : {r['n_incidents']} incidents, {r['n_regression_incidents']} regressions")
    for title, sec in (('NOVEL faults', r['novel']), ('PLANTED faults', r['planted'])):
        s = sec['summary']
        L.append(f"-- {title}: recall {s['hit']}/{s['total']}  exact-localised {s['exact_localisation']}  cause-correct {s['cause_correct']}  mean lag {s['mean_lag_days']}")
        for f in sec['faults']:
            L.append(f"   {f['id']:<3} {'HIT ' if f['hit'] else 'MISS'} {str(f['type'])[:26]:<26} {f['tenant']:<17} {json.dumps(f['cohort'])[:48]:<48} "
                     f"d{f['onset_day']}+{f['duration_days']} tier={f['magnitude_tier']:<7} lag={f['lag_days']} loc={f['localisation']} cause_ok={f['cause_correct']}")
    for k in ('by_magnitude_tier', 'by_shape', 'by_dimension', 'by_has_config_row'):
        L.append(f"   novel {k}: " + ', '.join(f"{a}={v['hit']}/{v['total']}" for a, v in r['novel'][k].items()))
    L.append(f"-- BENIGN: {r['benign']['pass']}/{r['benign']['total']} pass")
    for b in r['benign']['events']:
        L.append(f"   {b['id']} {b['type']:<32} {b['result']} examined={b['examined']} offending={b['offending_incidents']}")
    L.append(f"-- DECOYS: {r['decoys']['false_alarms']} false alarms")
    for d in r['decoys']['events']:
        L.append(f"   {d['id']} {str(d['kind']):<24} {d['tenant']:<17} {d['result']} {d['offending_incidents']}")
    L.append(f"-- FALSE POSITIVES: {len(r['false_positives'])}")
    for f in r['false_positives']:
        L.append(f"   {f}")
    L.append(f"-- PRECISION: {r['precision']}")
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bench-dir', required=True)
    ap.add_argument('--incidents', required=True)
    ap.add_argument('--json', action='store_true', help='print machine-readable JSON instead of text')
    a = ap.parse_args()
    r = evaluate(a.bench_dir, a.incidents)
    print(json.dumps(r, indent=1) if a.json else render(r))


if __name__ == '__main__':
    main()
