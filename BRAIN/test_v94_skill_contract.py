"""Synthetic crystallization only; no real input, models, or persistent databases."""
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from skill_loader import DynamicSkillLoader, normalize_skill_result
from rem_sleep_engine import REMSleepEngine
import numpy as np
from qfhrr_core import QFHRRHyperdimensionalEngine

def test_legacy_payload_is_not_execution():
    result=normalize_skill_result({'status':'COMPLETED','mode':'CRYSTALLIZED_ZERO_LLM','payload':{}})
    assert result['status']=='PROPOSAL_ONLY' and result['executed'] is False and result['verified'] is False
    assert normalize_skill_result({'status':'COMPLETED','mode':'OTHER'})['status']=='COMPLETED'

def test_new_crystallized_skill_is_proposal(tmp_path):
    @contextmanager
    def snapshot(**kwargs):
        yield [{'context_key':'abc','intent':'synthetic','pipeline_spec':'{"passos": []}','consecutive_successes':5}]
    engine=REMSleepEngine(skills_dir=tmp_path,pdag_engine=SimpleNamespace(node_snapshot=snapshot))
    assert engine.crystallize_habits_to_skills()==['synthetic']
    loader=DynamicSkillLoader(tmp_path)
    result=asyncio.run(loader.execute_skill('synthetic'))
    assert result['status']=='PROPOSAL_ONLY' and result['executed'] is False

def test_kernel_skill_entry_does_not_claim_success():
    from BRAINNET import BrainnetBridge
    bridge=object.__new__(BrainnetBridge)
    bridge._kernel=SimpleNamespace(skill_registry={'demo':lambda:{'status':'COMPLETED','mode':'CRYSTALLIZED_ZERO_LLM'}})
    result=bridge.run_skill('demo','execute',{})
    assert result['ok'] is False and result['result']['status']=='PROPOSAL_ONLY'

def test_vectorized_packing_matches_legacy_bytes():
    def reference(values):
        flat=np.asarray(values).astype(np.uint32);flat=np.pad(flat,(0,(-len(flat))%8))
        out=bytearray()
        for c in flat.reshape(-1,8):
            out.extend([int((c[0]&7)|((c[1]&7)<<3)|((c[2]&3)<<6)),
                        int(((c[2]>>2)&1)|((c[3]&7)<<1)|((c[4]&7)<<4)|((c[5]&1)<<7)),
                        int(((c[5]>>1)&3)|((c[6]&7)<<2)|((c[7]&7)<<5))])
        return bytes(out)
    rng=np.random.default_rng(42)
    for n in list(range(33))+[127,256,10000]:
        engine=QFHRRHyperdimensionalEngine(dimension=n)
        v=rng.integers(0,32,n,dtype=np.uint8)
        assert engine.pack_to_bits(v)==reference(v)
        np.testing.assert_array_equal(engine.unpack_from_bits(engine.pack_to_bits(v),n),v&7)
