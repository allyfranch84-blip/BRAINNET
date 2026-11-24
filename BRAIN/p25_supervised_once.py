"""Supervised one-shot harness. No action before exact approval on stdin."""
import asyncio,json,sys,threading,time,uuid
from pathlib import Path
from capability_lab import observe_physical_monitor
from execution_authority import PhysicalMoveProposal,PhysicalMoveApproval,authorization_scope
from actuator_bridge import ActuatorBridge
from effector import Effector

obs=observe_physical_monitor()
if obs.get('status')!='OBSERVED': print(json.dumps({'status':'ACTION_BLOCKED','reason':'OBSERVATION_UNAVAILABLE'}),flush=True);sys.exit(1)
x,y=obs['cursor'];l,t,r,b=obs['monitor_rect']
choices=[(x+10,y),(x-10,y),(x,y+10),(x,y-10)]
target=next((p for p in choices if l <= p[0] < r and t <= p[1] < b),None)
if target is None:print(json.dumps({'status':'ACTION_BLOCKED','reason':'MONITOR_BOUNDARY'}),flush=True);sys.exit(1)
proposal=PhysicalMoveProposal(uuid.uuid4().hex,uuid.uuid4().hex,(x,y),target,obs['monitor'],tuple(obs['monitor_rect']),0,time.monotonic()+300)
approval=PhysicalMoveApproval(proposal)
confirmation = f'APROVO {proposal.proposal_id} {proposal.task_id} {x} {y} {target[0]} {target[1]} {proposal.monitor} {proposal.tolerance}'
state_path = Path(__file__).resolve().parent / ('p27_' + proposal.proposal_id + '.json')
def record(data):
 state_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
pending={'status':'PENDING_APPROVAL','task_id':proposal.task_id,'proposal_id':proposal.proposal_id,'start':proposal.start,'target':proposal.target,'monitor':proposal.monitor,'monitor_rect':proposal.monitor_rect,'tolerance':proposal.tolerance,'expires_seconds':300,'observation_timestamp':obs['timestamp'],'coordinate_space':obs['coordinate_space'],'neutral_area_evidence':'operator assertion'}
record(pending)
print(json.dumps(pending,ensure_ascii=False,indent=2),flush=True)
print('Para aprovar exatamente esta proposta, digite a linha seguinte; Enter vazio cancela:',flush=True)
print(confirmation,flush=True)
line=sys.stdin.readline().strip()
if line!=confirmation:
 approval.cancel();result={'status':'CANCELLED','dispatched':False,'proposal_id':proposal.proposal_id};record(result);print(json.dumps(result),flush=True);sys.exit(0)
if not approval.approve_explicitly(proposal.proposal_id):
 result={'status':'ACTION_BLOCKED','code':'APPROVAL_EXPIRED','proposal_id':proposal.proposal_id};record(result);print(json.dumps(result),flush=True);sys.exit(1)
async def run():
 bridge=ActuatorBridge(effector_instance=Effector(),max_workers=1)
 token=threading.Event()
 with authorization_scope(token):
  await bridge.start()
  try:
   result=await bridge.dispatch('mouse_move_physical',{'approval':approval,'proposal':proposal},timeout_sec=10)
   outcome={'status':'DISPATCH_RESULT','bridge_status':result.status,'result':result.result,'error':result.error,'task_id':proposal.task_id,'proposal_id':proposal.proposal_id};record(outcome);print(json.dumps(outcome,ensure_ascii=False,indent=2),flush=True)
  finally:
   token.set();await bridge.stop()
asyncio.run(run())
