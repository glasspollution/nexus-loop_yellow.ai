#!/usr/bin/env python
"""Run evaluate.py over every bench-0N corpus.

usage: python evaluate_all.py --incidents-dir <dir with incidents-bench-0N.json> [--split dev|test|all] [--bench-root <bench>] [--json]
A missing incidents file is scored as an empty incident list and flagged.
"""
import argparse, json, os, sys, tempfile
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate as ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--incidents-dir', required=True)
    ap.add_argument('--split', default='all', choices=['dev', 'test', 'all'])
    ap.add_argument('--bench-root', default=HERE)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    results, missing = [], []
    for name in sorted(os.listdir(a.bench_root)):
        kp = os.path.join(a.bench_root, name, 'answer_key.json')
        if not (name.startswith('bench-') and os.path.isfile(kp)):
            continue
        split = json.load(open(kp))['split']
        if a.split != 'all' and split != a.split:
            continue
        ip = os.path.join(a.incidents_dir, f'incidents-{name}.json')
        if not os.path.isfile(ip):
            missing.append(name)
            tf = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False); json.dump({'incidents': []}, tf); tf.close(); ip = tf.name
        results.append(ev.evaluate(os.path.join(a.bench_root, name), ip))

    comb = {'novel_hit': 0, 'novel_total': 0, 'planted_hit': 0, 'planted_total': 0, 'benign_pass': 0, 'benign_total': 0,
            'decoy_false_alarms': 0, 'false_positives': 0, 'regressions': 0, 'tp': 0, 'exact_localised': 0, 'cause_correct': 0}
    by = {k: defaultdict(lambda: [0, 0]) for k in ('magnitude_tier', 'shape', 'dimension', 'has_config_row')}
    for r in results:
        n, p = r['novel']['summary'], r['planted']['summary']
        comb['novel_hit'] += n['hit']; comb['novel_total'] += n['total']; comb['planted_hit'] += p['hit']; comb['planted_total'] += p['total']
        comb['exact_localised'] += n['exact_localisation']; comb['cause_correct'] += n['cause_correct']
        comb['benign_pass'] += r['benign']['pass']; comb['benign_total'] += r['benign']['total']
        comb['decoy_false_alarms'] += r['decoys']['false_alarms']; comb['false_positives'] += len(r['false_positives'])
        comb['regressions'] += r['n_regression_incidents']
        if r['precision'] is not None: comb['tp'] += round(r['precision'] * r['n_regression_incidents'])
        for f in r['novel']['faults']:
            for k in by:
                by[k][str(f[k])][1] += 1; by[k][str(f[k])][0] += int(f['hit'])
    comb['precision'] = round(comb['tp'] / comb['regressions'], 3) if comb['regressions'] else None
    comb['by'] = {k: {kk: f'{v[0]}/{v[1]}' for kk, v in sorted(d.items())} for k, d in by.items()}
    if a.json:
        print(json.dumps({'split': a.split, 'missing_incident_files': missing, 'corpora': results, 'combined': comb}, indent=1)); return
    hdr = f"{'corpus':<9} {'split':<5} {'novel':>6} {'exact':>5} {'cause':>5} {'lag':>5} {'planted':>7} {'benign':>6} {'decoyFA':>7} {'FP':>3} {'prec':>5}"
    print(hdr); print('-' * len(hdr))
    for r in results:
        n, p = r['novel']['summary'], r['planted']['summary']
        print(f"{r['corpus']:<9} {r['split']:<5} {n['hit']:>2}/{n['total']:<3} {n['exact_localisation']:>5} {n['cause_correct']:>5} {str(n['mean_lag_days']):>5} "
              f"{p['hit']:>3}/{p['total']:<3} {r['benign']['pass']:>2}/{r['benign']['total']:<3} {r['decoys']['false_alarms']:>7} {len(r['false_positives']):>3} {str(r['precision']):>5}")
    print('-' * len(hdr))
    c = comb
    print(f"{'TOTAL':<9} {a.split:<5} {c['novel_hit']:>2}/{c['novel_total']:<3} {c['exact_localised']:>5} {c['cause_correct']:>5} {'':>5} "
          f"{c['planted_hit']:>3}/{c['planted_total']:<3} {c['benign_pass']:>2}/{c['benign_total']:<3} {c['decoy_false_alarms']:>7} {c['false_positives']:>3} {str(c['precision']):>5}")
    for k, d in c['by'].items():
        print(f"novel recall by {k}: " + ', '.join(f'{kk}={v}' for kk, v in d.items()))
    if missing:
        print('WARNING: missing incidents files scored as empty:', ', '.join(missing))


if __name__ == '__main__':
    main()
