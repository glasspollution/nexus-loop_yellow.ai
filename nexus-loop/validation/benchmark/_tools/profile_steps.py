import json,gzip,collections as C,sys,datetime as dt
K=sys.argv[1]
S={}
for l in gzip.open(K+'/corpus/sessions.jsonl.gz','rt'):
    s=json.loads(l); S[s['session_id']]=s
keys=C.Counter(); by=C.defaultdict(list)
tool_intent=C.Counter(); outc=C.Counter(); ec=C.Counter(); sc=C.Counter()
mism=C.Counter(); examples={}
cur=None; rows=[]
def check(sid,rows):
    s=S[sid]
    te=sum(1 for r in rows if r['step_type']=='tool_call' and r['outcome']!='ok')
    km=sum(1 for r in rows if r['step_type']=='kb_lookup' and not r.get('kb_hit'))
    gb=sum(1 for r in rows if r['step_type']=='guardrail' and r['outcome']=='blocked')
    cost=round(sum(r.get('cost_usd',0) or 0 for r in rows if r['step_type']=='llm_call'),6)
    nt=max(r['turn_index'] for r in rows)
    ms=[r['milestone'] for r in rows if r.get('milestone')]
    hs=sum(1 for r in rows if r['step_type']=='handoff')
    mism['te']+= te!=s['tool_error_count']; mism['km']+= km!=s['kb_miss_count']; mism['gb']+=gb!=s['guardrail_blocks']
    mism['cost']+= abs(cost-s['cost_usd'])>1e-5; mism['turns']+= nt!=s['turns']; mism['ms']+= ms!=s['milestones_reached']
    mism['handoffstep_vs_end']+= (hs>0)!=(s['session_end']=='handoff')
    mism['seqs']+= [r['step_seq'] for r in rows]!=list(range(1,len(rows)+1))
    mism['day']+= any(r['day']!=s['day'] for r in rows)
    t0=dt.datetime.fromisoformat(s['ts_start']);t1=dt.datetime.fromisoformat(s['ts_end'])
    mism['dur']+= abs((t1-t0).total_seconds()-s['duration_s'])>1.5
    mism['first_ts']+= rows[0]['ts']!=s['ts_start']
    sm=(sum(r['duration_ms'] for r in rows)/1000)
    C_ratio.append(s['duration_s']/max(sm,0.001))
    tag=(s['session_end'],s['handoff_by_design'],te>0,gb>0,s['agent_kind'])
    if tag not in examples: examples[tag]=(s,rows)
    pat=tuple(r['step_type'] for r in rows); pats[(s['agent_kind'])][pat[:12]]+=1
C_ratio=[]; pats=C.defaultdict(C.Counter)
n=0
for l in gzip.open(K+'/corpus/agent_steps.jsonl.gz','rt'):
    r=json.loads(l); n+=1
    keys[(r['step_type'],tuple(sorted(r.keys())))]+=1
    st=r['step_type']
    outc[(st,r['outcome'],r['error_class'],r.get('status_code'))]+=1
    if st=='tool_call': tool_intent[(r['tenant'],r['intent'],r['tool_name'],r.get('tool_version'))]+=1
    if st in('llm_call','tool_call') : ec[(st,r.get('retry_count'))]+=1
    if st=='kb_lookup': sc[(r['kb_hit'], round(r['kb_top_score'],1))]+=1
    if st=='guardrail': sc[('g',r['intent'],r['outcome'])]+=1
    if r['session_id']!=cur:
        if cur: check(cur,rows)
        cur=r['session_id']; rows=[]
    rows.append(r)
check(cur,rows)
print('nsteps',n)
for k,v in keys.items(): print(v,k)
for k,v in sorted(outc.items(),key=lambda x:-x[1]): print(v,k)
print(sorted(tool_intent.items()))
print(ec); print(sorted(sc.items(),key=str))
print(mism)
C_ratio.sort(); print('dur ratio quantiles',[round(C_ratio[int(q*len(C_ratio))],2) for q in (0.05,.25,.5,.75,.95)])
for ak,p in pats.items(): print(ak,p.most_common(6))
for tag,(s,rows) in list(examples.items())[:14]:
    print('\n==',tag,json.dumps(s))
    for r in rows: print('  ',{k:v for k,v in r.items() if k not in('tenant','agent_id','agent_kind','channel','intent','model','prompt_version','kb_version','session_id','day')})
