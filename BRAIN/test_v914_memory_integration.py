"""Mock-only command/memory verification; never starts Kernel or actuator."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from BRAINNET import BrainnetBridge, BrainnetKernel, _situation_task
from situation_memory import SituationMemory
from situation_fhrr_index import SituationFHRRIndex
from execution_authority import require_action_allowed

class FakeVSA:
    dim = 4
    def text_to_hypervector(self, text):
        return np.array([1, 1j, 1, 1j], dtype=np.complex64)
    def similarity(self, left, right): return 1.0

def make_bridge(enabled):
    kernel=object.__new__(BrainnetKernel)
    kernel.esta_dormindo=False; kernel.ultimo_toque_ai=0
    kernel._situation_lock=threading.RLock()
    kernel.situation_memory=SituationMemory(enabled=True) if enabled else None
    kernel.situation_index=SituationFHRRIndex(FakeVSA()) if enabled else None
    kernel.router=SimpleNamespace(read_situation=lambda memory,task: memory.snapshot(task))
    bridge=object.__new__(BrainnetBridge);bridge._kernel=kernel;bridge._window=None;bridge._chat_history=[]
    return bridge,kernel

def test_command_retrieves_evidence_and_records_verified_outcome():
    bridge,kernel=make_bridge(True)
    planner=Mock(return_value={'plan':'read-only simulated'})
    def simulated_dispatch(*args):
        require_action_allowed('EXECUTE')
        evidence=kernel.read_situation_evidence(_situation_task.get())
        assert evidence['execution_authorized'] is False
        assert evidence['matches'] and evidence['matches'][0]['snapshot'].source=='kernel'
        planner(evidence)
        return {'reply':'ok','logs':[], 'visual_result':{'sucesso_real':True,'goal_state':'GOAL_VERIFIED'}}
    bridge._executar_comando_interno=simulated_dispatch
    bridge.send_command('mostre informação')
    planner.assert_called_once()
    items=list(kernel.situation_memory._items.values())
    assert any(item.value['state']=='goal_verified' and item.verified for item in items)
    assert any(item.value['state']=='task_finished' for item in items)

def test_disabled_memory_does_not_change_dispatch():
    bridge,kernel=make_bridge(False)
    bridge._executar_comando_interno=Mock(return_value={'reply':'ok','logs':[]})
    bridge.send_command('mostre informação')
    assert kernel.read_situation_evidence('none') is None
    bridge._executar_comando_interno.assert_called_once()

def test_ghrr_similar_proposal_requires_matching_context_and_provenance():
    from ghrr_core import GHRRHyperdimensionalEngine
    from pdag_ghrr_extension import SyntacticPDAG
    planner=object.__new__(SyntacticPDAG);planner.engine=GHRRHyperdimensionalEngine(dim=128)
    context={'process':'paint','window':'7','target':'canvas'}
    steps=[{'acao':'CLICK'},{'acao':'DRAG'}]
    good={'context':context,'source':'synthetic','historical_verified':True,'steps':steps}
    wrong={**good,'context':{**context,'window':'8'}}
    unverified={**good,'historical_verified':False}
    proposals=planner.propose_similar(steps,context,[wrong,unverified,good])
    assert len(proposals)==1 and proposals[0]['execution_authorized'] is False
    assert proposals[0]['similarity'] > .99
    assert planner.propose_similar(steps,{},[good]) == []
