"""Explicit safe regression selection; never discovers or runs arbitrary tests."""
import argparse, datetime, hashlib, json, os, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parent
GUI=ROOT.parent/'INTERFACE DE USUARIO'/'BRAINDET IU'/'project'
LOGS=ROOT/'development_logs'
BASELINE=ROOT/'regression_baseline_v2.json'
GROUPS={
 'fast':['test_regression_runner.py','test_v98a2_7_motor_preparation.py','test_v98a2_1_safe_trajectory.py','test_v98a2_9_1_atomic.py','test_v98a2_9_pending.py','test_v98a2_8_motor_path.py','test_v909_foundation.py'],
 'integration':['test_v98a_capability_lab.py::test_natural_input_reaches_proposal_without_motor','test_v97r22_production.py','test_v97r23_budget.py','test_v97r24_coverage.py','test_inference_backend.py','test_v951_intent.py'],
 'visual_history':['test_ui_tars_protocol.py::'+s for s in (
  'test_bridge_click_moves_then_clicks_under_lock','test_vision_sends_image_schema_and_unloads_model',
  'test_kernel_bridge_passes_direct_instruction_without_browser_url','test_failed_ncd_stops_before_next_action',
  'test_finished_without_verified_action_never_claims_success','test_focus_change_blocks_input_before_actuation')],
}
# Unknown paths deliberately trigger the whole audited selection, never test discovery.
MAP={
 'execution_authority.py':['fast','integration'],
 'adaptive_resource_controller.py':['fast','integration'], 'BRAINNET.py':['fast','integration'],
 'capability_lab.py':['fast','integration'], 'parser_contract.py':['fast','integration'],
 'inference_backend.py':['integration'], 'situation_memory.py':['fast'],
 'router.py':['integration'], 'system_intent.py':['integration'],
 'ui_tars_protocol.py':['fast','integration'], 'vision_eye.py':['fast','integration'],
 'regression_runner.py':['fast','integration'],
}

VISUAL_DIAGNOSTIC = 'test_v98a_capability_lab.py::test_move_requires_authorization_and_independent_observation'

def run_visual_diagnostic(*, timeout=12, test_id=VISUAL_DIAGNOSTIC):
 """Isolated audited test only; no external networking is enabled here."""
 if test_id != VISUAL_DIAGNOSTIC or not 5 <= timeout <= 30:
  raise ValueError('diagnóstico não auditado')
 LOGS.mkdir(exist_ok=True)
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 prefix=LOGS/('REGRESSION_VISUAL_'+stamp)
 log=Path(str(prefix)+'.log'); xml=Path(str(prefix)+'.xml')
 env=os.environ.copy(); env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
 cmd=[sys.executable,'-m','pytest','-vv','-s','-p','no:cacheprovider',
      '-o','faulthandler_timeout=4','--junitxml='+str(xml),test_id]
 with log.open('w',encoding='utf-8') as output:
  try:
   process=subprocess.run(cmd,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=timeout,check=False)
   status='PASS' if process.returncode==0 else 'FAIL' if process.returncode==1 else 'ERROR'
   code=process.returncode
  except subprocess.TimeoutExpired:
   output.write('\nTIMEOUT: processo de teste isolado encerrado após prazo\n')
   status,code='TIMEOUT',None
 result={'test_id':test_id,'status':status,'exit_code':code,'log':str(log),
         'junit':str(xml) if xml.exists() else None,'timeout_seconds':timeout}
 Path(str(prefix)+'_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 return result

def digest(message): return hashlib.sha256(message.encode('utf-8')).hexdigest()
def cases(path):
 root=ET.parse(path).getroot(); result={}
 for c in root.iter('testcase'):
  name=c.get('classname','')+'::'+c.get('name','')
  child=c.find('failure'); error=c.find('error'); skipped=c.find('skipped')
  problem=child if child is not None else error
  status='failed' if child is not None else 'error' if error is not None else 'skipped' if skipped is not None else 'passed'
  msg=problem.get('message','') if problem is not None else ''
  result[name]={'status':status,'failure_signature':digest(msg) if problem is not None else None,'message':msg[:500]}
 return result

def run(args,cwd,log,env=None):
 with log.open('w',encoding='utf-8') as f:
  try: return subprocess.run(args,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=300,check=False).returncode
  except subprocess.TimeoutExpired:
   f.write('\nTIMEOUT: processo de teste excedeu 300 s\n'); return 124

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--suite',choices=['fast','integration','safe-full','gui','visual-diagnostic','e2e-supervised'],default='safe-full')
 p.add_argument('--changed',action='append',default=[],help='caminho alterado; repetível')
 p.add_argument('--record-baseline',action='store_true',help='criar baseline inicial somente se ainda não existir')
 args=p.parse_args(); LOGS.mkdir(exist_ok=True)
 if args.suite=='visual-diagnostic':
  result=run_visual_diagnostic()
  print(json.dumps(result,ensure_ascii=False,indent=2))
  return 0 if result['status']=='PASS' else 1
 if args.suite=='e2e-supervised':
  print('E2E supervisionado não possui seleção auditada; nada executado.'); return 2
 selected={'fast':['fast'],'integration':['integration'],'safe-full':['fast','integration'],'gui':[]}[args.suite]
 gui=args.suite=='gui'
 if args.changed:
  selected=[]
  for name in args.changed:
   normalized=name.replace('\\','/').lower()
   if 'project/project/' in normalized: print('Cópia aninhada não é GUI oficial:',name); continue
   if 'interface de usuario/' in normalized or 'interface de usuário/' in normalized:
    gui=True; continue
   base=Path(normalized).name
   related=MAP.get(base)
   if related is None:
    if base.startswith('test_') and any(base==item.split('::')[0].lower() for g,group in GROUPS.items() if g != 'visual_history' for item in group):
     related=[g for g,items in GROUPS.items() if g != 'visual_history' and any(base==item.split('::')[0].lower() for item in items)]
    else: related=['fast','integration']
   selected.extend(related)
 selected=list(dict.fromkeys(selected)); targets=list(dict.fromkeys(t for g in selected for t in GROUPS[g]))
 stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'); prefix=LOGS/('REGRESSION_'+stamp)
 results={}; code=0; xml=Path(str(prefix)+'.xml'); test_log=Path(str(prefix)+'.log')
 if targets:
  env=os.environ.copy(); env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
  cmd=[sys.executable,'-m','pytest','-q','--tb=short','-p','no:cacheprovider','--junitxml='+str(xml),*targets]
  code=run(cmd,ROOT,test_log,env)
  if xml.exists(): results=cases(xml)
  else: print('ERRO: pytest não gerou JUnit; consulte',test_log); return 2
 gui_results={}
 if gui:
  package=json.loads((GUI/'package.json').read_text(encoding='utf-8')); scripts=package.get('scripts',{})
  for script in ('build','test','typecheck'):
   if script not in scripts: gui_results[script]='NOT_CONFIGURED'; continue
   npm='npm.cmd' if os.name=='nt' else 'npm'
   rc=run([npm,'run',script],GUI,Path(str(prefix)+'_gui_'+script+'.log'))
   gui_results[script]=rc
   if rc: code=1
 if args.record_baseline:
  if BASELINE.exists(): print('Baseline já existe; não sobrescrita.'); return 2
  if not results or code not in (0,1): print('Execução incompleta: baseline não criada.'); return 2
  BASELINE.write_text(json.dumps({'version':2,'created':stamp,'selection':targets,'cases':results,
   'historical_visual_source':'V9_7_E1_R1_REPORT.md'},indent=2,ensure_ascii=False),encoding='utf-8')
 baseline=json.loads(BASELINE.read_text(encoding='utf-8')) if BASELINE.exists() else None
 new=[]; known=[]; changed=[]; missing=[]; new_skips=[]
 for name,item in results.items():
  old=baseline.get('cases',{}).get(name) if baseline else None
  if item['status']=='skipped' and old and old['status']=='passed': new_skips.append(name)
  if item['status'] not in ('failed','error'): continue
  if old and old['status']==item['status'] and old['failure_signature']==item['failure_signature']: known.append(name)
  elif old and old['status'] in ('failed','error'): changed.append(name)
  else: new.append(name)
 if baseline and targets == baseline.get('selection'):
  missing=sorted(set(baseline['cases'])-set(results))
 counts={s:sum(v['status']==s for v in results.values()) for s in ('passed','failed','error','skipped')}
 summary={'timestamp':stamp,'groups':selected,'targets':targets,'counts':counts,'known_failures':known,'new_failures':new,'changed_failures':changed,'new_skips':new_skips,'missing_baseline_cases':missing,
          'baseline_available':bool(baseline),'gui':gui_results,'pytest_exit':code,'junit':str(xml) if targets else None,
          'e2e':'NOT_RUN: no audited selection','historical_visual_tests':GROUPS['visual_history'],
          'historical_visual_source':'V9_7_E1_R1_REPORT.md; historical results are not current observations',
          'limitations':'Only explicitly allowlisted tests; visual async tests can hang in this environment; baseline captures signatures, not proof of safety.'}
 Path(str(prefix)+'_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps(summary,indent=2,ensure_ascii=False))
 if not baseline and results: return 2
 if code not in (0,1): return 2
 if new or changed or new_skips or missing or any(v not in (0,'NOT_CONFIGURED') for v in gui_results.values()): return 1
 return 0
if __name__=='__main__': sys.exit(main())
