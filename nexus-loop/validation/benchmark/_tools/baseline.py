import json,gzip,collections as C,sys,statistics as st
K=sys.argv[1]
S={}
for l in gzip.open(K+'/corpus/sessions.jsonl.gz','rt'):
    s=json.loads(l); S[s['session_id']]=s
def rate(xs): return round(sum(xs)/max(1,len(xs)),4), len(xs)
res=C.defaultdict(list)
for s in S.values():
    r=s['session_end']=='resolved'
    for dim,val in [('intent',s['intent']),('agent',s['agent_id']),('channel',s['channel']),('segment',s['custom_dims']['segment'])]:
        res[(s['tenant'],dim,val)].append(r)
        res[(s['tenant'],dim+'_abandon',val)].append(s['session_end']=='abandoned')
        res[(s['tenant'],dim+'_unplanned_ho',val)].append(s['session_end']=='handoff' and not s['handoff_by_design'])
        res[(s['tenant'],dim+'_guard',val)].append(s['guardrail_blocks']>0)
for k in sorted(res): print(k, rate(res[k]))
tool=C.defaultdict(list); tdur=C.defaultdict(list); llm=C.defaultdict(list); ldur=C.defaultdict(list); ltok=C.defaultdict(list); kb=C.Counter()
g=C.Counter()
for l in gzip.open(K+'/corpus/agent_steps.jsonl.gz','rt'):
    r=json.loads(l); st_=r['step_type']
    if st_=='tool_call':
        tool[(r['tenant'],r['tool_name'])].append(r['outcome']!='ok'); tdur[(r['tenant'],r['tool_name'])].append(r['duration_ms'])
    elif st_=='llm_call':
        llm[r['agent_id']].append(r['outcome']!='ok'); ldur[r['agent_id']].append(r['duration_ms']); ltok[r['agent_id']].append(r['output_tokens'])
    elif st_=='kb_lookup': kb[(r['tenant'],r['intent'],r['agent_kind'])]+=1
    elif st_=='guardrail': g[(r['tenant'],r['intent'],r['turn_index'])]+=1
for k in sorted(tool): print('tool',k,rate(tool[k]),'dur med',st.median(tdur[k]),'mean',round(st.mean(tdur[k])))
for k in sorted(llm): print('llm',k,rate(llm[k]),'dur med',st.median(ldur[k]),'mean',round(st.mean(ldur[k])),'outtok',round(st.mean(ltok[k])))
print(sorted(kb.items()))
print(sorted(g.items())[:40])
