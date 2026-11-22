"""Synthetic artifacts only; no process, network, or real model."""
import hashlib
import pytest
from inference_backend import validate_model_artifacts, ConfigurationError
from unittest.mock import Mock, patch

def test_explicit_model_sha256_and_legacy_behavior(tmp_path):
    model=tmp_path/'tiny.gguf';model.write_bytes(b'GGUFsynthetic')
    expected=hashlib.sha256(model.read_bytes()).hexdigest()
    assert validate_model_artifacts(str(model))['model']==str(model)
    assert validate_model_artifacts(str(model), expected_model_sha256=expected)['model']==str(model)
    with pytest.raises(ConfigurationError,match='nao confere'):
        validate_model_artifacts(str(model),expected_model_sha256='0'*64)
    with pytest.raises(ConfigurationError,match='invalido'):
        validate_model_artifacts(str(model),expected_model_sha256='bad')

def test_bad_digest_cannot_launch_server(tmp_path):
    from inference_backend import LlamaProcessManager
    exe=tmp_path/'llama-server.exe';exe.write_bytes(b'synthetic executable')
    model=tmp_path/'tiny.gguf';model.write_bytes(b'GGUFsynthetic')
    popen=Mock()
    manager=LlamaProcessManager(str(exe),str(model),expected_model_sha256='0'*64,
                                probe=lambda:False,port_probe=lambda *_:False,popen=popen)
    with pytest.raises(ConfigurationError,match='nao confere'):manager.start()
    popen.assert_not_called()

def test_procedural_lookup_requires_context_and_verified_evidence():
    from pdag_engine import MyelinatedPDAGEngine
    engine=object.__new__(MyelinatedPDAGEngine)
    route={'passos':[{'acao':'CLICK'}],'__meta__':{'teacher_verified':True}}
    with patch.object(MyelinatedPDAGEngine,'find_myelinated_path',return_value=route) as lookup:
        assert engine.propose_verified_procedure('trajectory:x',{}) is None
        lookup.assert_not_called()
        result=engine.propose_verified_procedure('trajectory:x',{'hwnd':1,'pid':2})
        assert result['status']=='PROPOSED' and result['execution_authorized'] is False
        assert result['context_revalidation_required'] is True
    with patch.object(MyelinatedPDAGEngine,'find_myelinated_path',return_value={'passos':route['passos'],'__meta__':{}}):
        assert engine.propose_verified_procedure('trajectory:x',{'hwnd':1,'pid':2}) is None

def test_proposal_does_not_authorize_simulated_action():
    import threading
    from execution_authority import authorization_scope, require_action_allowed
    from pdag_engine import MyelinatedPDAGEngine
    engine=object.__new__(MyelinatedPDAGEngine)
    route={'passos':[{'acao':'CLICK'}],'__meta__':{'teacher_verified':True}}
    with patch.object(MyelinatedPDAGEngine,'find_myelinated_path',return_value=route):
        proposal=engine.propose_verified_procedure('trajectory:x',{'hwnd':1,'pid':2})
    assert proposal['status']=='PROPOSED' and not proposal['execution_authorized']
    with pytest.raises(PermissionError): require_action_allowed('CLICK')
    with authorization_scope(threading.Event()):
        require_action_allowed('CLICK')
        executed={'executed':True,'observed':False}
    # A simulated dispatch alone cannot establish the final goal.
    assert executed['executed'] and not executed['observed']
