"""Internal-consistency checks on a written corpus (sessions vs steps vs turns vs feedback vs manifest)."""
import json, gzip, sys, collections as C, datetime as dt, csv
d = sys.argv[1]
S = {}
dup = 0
for l in gzip.open(d + '/corpus/sessions.jsonl.gz', 'rt'):
    s = json.loads(l); dup += s['session_id'] in S; S[s['session_id']] = s
mm = C.Counter(); cur = None; rows = []; seen = set(); stc = C.Counter(); nsteps = 0
def chk(sid, rows):
    s = S.get(sid)
    if s is None: mm['orphan_steps'] += 1; return
    seen.add(sid)
    te = sum(1 for r in rows if r['step_type'] == 'tool_call' and r['outcome'] != 'ok')
    km = sum(1 for r in rows if r['step_type'] == 'kb_lookup' and not r['kb_hit'])
    gb = sum(1 for r in rows if r['step_type'] == 'guardrail' and r['outcome'] == 'blocked')
    ok = sum(r['cost_usd'] for r in rows if r['step_type'] == 'llm_call' and r['outcome'] == 'ok')
    mm['tool_error_count'] += te != s['tool_error_count']; mm['guardrail_blocks'] += gb != s['guardrail_blocks']
    mm['kb_miss_count(expected only for instrumentation benign)'] += km != s['kb_miss_count']
    mm['cost_ok_sum'] += abs(ok - s['cost_usd']) > 1e-5
    mm['turns'] += max(r['turn_index'] for r in rows) != s['turns']
    hs = [r for r in rows if r['step_type'] == 'handoff']
    mm['handoff_step_vs_end'] += (len(hs) > 0) != (s['session_end'] == 'handoff')
    if hs: mm['handoff_flag'] += hs[0]['handoff_by_design'] != s['handoff_by_design']; mm['handoff_ts_end'] += hs[-1]['ts'] != s['ts_end']
    mm['step_seq'] += [r['step_seq'] for r in rows] != list(range(1, len(rows) + 1))
    mm['day'] += any(r['day'] != s['day'] for r in rows)
    mm['agent_field'] += any(r['agent_id'] != s['agent_id'] or r['model'] != s['model'] or r['prompt_version'] != s['prompt_version'] for r in rows)
    mm['first_ts'] += rows[0]['ts'] != s['ts_start']
    ts = [dt.datetime.fromisoformat(r['ts']) for r in rows]
    mm['ts_monotonic'] += any(b < a for a, b in zip(ts, ts[1:]))
    mm['ts_after_end'] += ts[-1] > dt.datetime.fromisoformat(s['ts_end'])
    mm['duration_s'] += abs((dt.datetime.fromisoformat(s['ts_end']) - dt.datetime.fromisoformat(s['ts_start'])).total_seconds() - s['duration_s']) >= 1.0
    mm['milestones_total'] += len(s['milestones_reached']) > s['milestones_total']
    mm['resolved_full_milestones'] += s['session_end'] == 'resolved' and len(s['milestones_reached']) != s['milestones_total']
    mm['v2_tool_rows'] += s['agent_kind'] == 'v2_flow' and any(r['step_type'] == 'tool_call' for r in rows)
for l in gzip.open(d + '/corpus/agent_steps.jsonl.gz', 'rt'):
    r = json.loads(l); nsteps += 1; stc[r['step_type']] += 1
    if r['session_id'] != cur:
        if cur: chk(cur, rows)
        if r['session_id'] in seen: mm['non_contiguous'] += 1
        cur = r['session_id']; rows = []
    rows.append(r)
chk(cur, rows)
mm['sessions_without_steps'] = len(set(S) - seen)
T = C.Counter(); ntu = 0
for l in gzip.open(d + '/corpus/turns.jsonl.gz', 'rt'):
    t = json.loads(l); T[t['session_id']] += 1; ntu += 1
mm['turn_rows_vs_turns'] = sum(1 for k, s in S.items() if T[k] != s['turns']) + sum(1 for k in T if k not in S)
fb = list(csv.DictReader(open(d + '/corpus/feedback.csv')))
mm['feedback_mismatch'] = sum(1 for f in fb if f['session_id'] not in S or S[f['session_id']]['csat'] != int(f['csat'])) + abs(len(fb) - sum(1 for s in S.values() if s['csat'] is not None))
m = json.load(open(d + '/manifest.json'))
mm['manifest_rows'] = (m['rows']['sessions'] != len(S)) + (m['rows']['agent_steps'] != nsteps) + (m['rows']['turns'] != ntu) + (m['rows']['csat_responses'] != len(fb)) + (m['step_type_counts'] != dict(stc))
cfg = list(csv.reader(open(d + '/corpus/config_timeline.csv')))
mm['config_sorted'] = int([int(r[0]) for r in cfg[1:]] != sorted(int(r[0]) for r in cfg[1:])); mm['config_rows_manifest'] = int(m['rows']['config_changes'] != len(cfg) - 1)
mm['dup_session_ids'] = dup
print(d.split('/')[-1], {k: v for k, v in mm.items()})
