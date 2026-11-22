"""Synthetic-only HDC evaluation; no desktop, model server or persisted memory."""
import json, os, statistics, time, tracemalloc
from pathlib import Path
import numpy as np
from hyperdimensional import FHRRHyperdimensionalEngine
from ghrr_core import GHRRHyperdimensionalEngine
from qfhrr_core import QFHRRHyperdimensionalEngine

ACTIONS=('left','right','toggle')
STATES=[(x,f,b) for x in range(8) for f in (0,1) for b in (0,1)]
def step(s,a):
 x,f,b=s
 if a=='left': return (max(0,x-1),f,b)
 if a=='right': return (min(7,x+1),f,b)
 if a=='toggle': return (x,f,1-b) if f and x in (2,5) else s
 raise ValueError(a)

def percent(values,q): return float(np.percentile(values,q)) if values else None

def capacity(engine,n,noise,rng):
 keys=[engine.generate_vector() for _ in range(n)]
 values=[engine.generate_vector() for _ in range(n)]
 memory=engine.bundle([engine.bind(k,v) for k,v in zip(keys,values)])
 hits=0; false=0; sims=[]
 for k,v in zip(keys,values):
  if noise and isinstance(engine,FHRRHyperdimensionalEngine):
   k=k*np.exp(1j*rng.normal(0,noise,k.shape)).astype(np.complex64)
  estimate=engine.unbind_left(memory,k) if isinstance(engine,GHRRHyperdimensionalEngine) else engine.unbind(memory,k)
  scores=[engine.similarity(estimate,candidate) for candidate in values]
  hit=int(np.argmax(scores))==len(sims);hits+=hit;false+=not hit;sims.append(float(scores[len(sims)]))
 return {'records':n,'recall_top1':hits/n,'false_positive_rate':false/n,'mean_target_similarity':statistics.mean(sims),
         'persistent_vector_bytes':memory.nbytes+sum(a.nbytes for a in keys+values)}

def experiment(seed,dim=512):
 t0=time.perf_counter();rng=np.random.default_rng(seed)
 engine=FHRRHyperdimensionalEngine(dimension=dim,seed=seed)
 states={s:engine.generate_vector() for s in STATES};actions={a:engine.generate_vector() for a in ACTIONS}
 permutation=rng.permutation(len(STATES));train={STATES[i] for i in permutation[:24]};test=[STATES[i] for i in permutation[24:]]
 triples=[(s,a,step(s,a)) for s in sorted(train) for a in ACTIONS]
 keys=[engine.bind(states[s],actions[a]) for s,a,_ in triples]
 memory=engine.bundle([engine.bind(k,states[nxt]) for k,(_,_,nxt) in zip(keys,triples)])
 table={(s,a):nxt for s,a,nxt in triples};ordered=list(STATES)
 init_ms=(time.perf_counter()-t0)*1000
 def predict(s,a):
  key=engine.bind(states[s],actions[a]); est=engine.unbind(memory,key)
  score=np.asarray([engine.similarity(est,states[c]) for c in ordered]); ix=np.argsort(-score,kind='stable')
  return [ordered[i] for i in ix[:3]]
 sample={};lat={'reference':[],'table':[],'fhrr':[]};fp=0
 for horizon in (1,2,4,8):
  total=correct=recall=goals=discarded=table_hits=0
  for initial in test:
   truth=initial; pred=initial; valid=True
   for j in range(horizon):
    a=ACTIONS[(j+seed)%len(ACTIONS)]
    t=time.perf_counter_ns();nxt=step(truth,a);lat['reference'].append((time.perf_counter_ns()-t)/1000)
    t=time.perf_counter_ns();table_value=table.get((truth,a));lat['table'].append((time.perf_counter_ns()-t)/1000)
    table_hits+=table_value is not None
    t=time.perf_counter_ns();candidates=predict(pred,a);lat['fhrr'].append((time.perf_counter_ns()-t)/1000)
    actual=step(pred,a); recall+=actual in candidates; discarded+=actual not in candidates;fp+=sum(c!=actual for c in candidates)
    # Oracle exact verification is simulated and its cost excluded; no real-world authorization.
    if actual in candidates: pred=actual
    else: valid=False
    truth=nxt;total+=1;correct+=candidates[0]==actual
   goals+=valid and pred==truth
  sample[str(horizon)]={'trials':len(test),'steps':total,'top1_accuracy':correct/total,'top3_recall':recall/total,
    'false_elimination_rate':discarded/total,'verified_goal_rate':goals/len(test),
    'table_coverage':table_hits/total,'reference_accuracy':1.0}
 return {'seed':seed,'dimension':dim,'training_states':len(train),'heldout_initial_states':len(test),
         'leakage_note':'training triples may reach heldout destination states; heldout states never source in training',
         'initialization_ms':init_ms,'horizons':sample,'false_candidates':fp,
         'latency_us':{k:{'p50':percent(v,50),'p95':percent(v,95)} for k,v in lat.items()},
         'persistent_fhrr_array_bytes':memory.nbytes+sum(v.nbytes for v in states.values())+sum(v.nbytes for v in actions.values()),
         'exact_table_entries':len(table)}

def main():
 tracemalloc.start(); started=time.perf_counter(); rows=[]; experiments=[]
 try:
  import psutil
  rss_start=psutil.Process().memory_info().rss
 except ImportError: rss_start=None
 for seed in (11,29,47):
  for kind in ('FHRR','QFHRR','GHRR'):
   for n in (4,16,64):
    for noise in ((0,0.25) if kind=='FHRR' else (0,)):
     rng=np.random.default_rng(seed+4000+n)
     eng=FHRRHyperdimensionalEngine(dimension=512,seed=seed) if kind=='FHRR' else QFHRRHyperdimensionalEngine(dimension=512,seed=seed,sparsity=1.0) if kind=='QFHRR' else GHRRHyperdimensionalEngine(dim=256,seed=seed)
     rows.append({'seed':seed,'engine':kind,'noise_radians':noise,**capacity(eng,n,noise,rng)})
  experiments.append(experiment(seed))
 probe=FHRRHyperdimensionalEngine(dimension=512,seed=83)
 va,vb=probe.generate_vector(),probe.generate_vector()
 weighted=probe.bundle_weighted([va,vb],[3,1])
 phase={'weighted_similarity_a':probe.similarity(weighted,va),'weighted_similarity_b':probe.similarity(weighted,vb),
        'opposite_similarity':probe.similarity(va,probe.phase_shift(va,np.pi)),
        'note':'opposite phase is algebraic, not evidence of an incorrect action'}
 current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 rss_end=psutil.Process().memory_info().rss if rss_start is not None else None
 output={'seeds':[11,29,47],'capacity':rows,'rollouts':experiments,'python_allocation_peak_bytes':peak,
         'phase_experiment':phase,'rss_before_bytes':rss_start,'rss_after_bytes':rss_end,
         'vram':'NOT_MEASURED (CPU experiment)','llm_calls_avoided':'NOT_MEASURED; neither baseline uses an LLM',
         'duration_s':time.perf_counter()-started}
 path=Path(__file__).resolve().parent.parent/'development_logs'/'V9_8_X1_RESULTS.json';path.parent.mkdir(exist_ok=True)
 path.write_text(json.dumps(output,indent=2),encoding='utf-8');print(path)
if __name__=='__main__': main()
