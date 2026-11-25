"""Supervisor contracts, mocked processes and HTTP only."""
from unittest.mock import Mock,patch
from inference_supervisor import InferenceSupervisor,reset_inference_processes

def test_start_resets_once_and_probes_real_generation():
    with patch.dict('os.environ',{'BRAINNET_INFERENCE_BACKEND':'ollama','BRAINNET_MOTOR_MODEL':'qwen2.5:1.5b'}):
        s=InferenceSupervisor()
    responses=[{'version':'test'},{'models':[{'name':'qwen2.5:1.5b'}]},{'done':True,'response':'OK'}]
    with patch('inference_supervisor.reset_inference_processes') as reset,patch.object(s,'_spawn'),patch.object(s,'_alive',return_value=True),patch.object(s,'_json',side_effect=responses*2) as request:
        assert s.start(reset=True)
        assert s.start(reset=True)
        reset.assert_called_once()
        assert request.call_args_list[2].args[0]=='/api/generate'
        assert s.state=='READY'

def test_warmup_failure_not_reported_as_ready():
    s=InferenceSupervisor()
    with patch.object(s,'_spawn'),patch.object(s,'_warmup',side_effect=RuntimeError('runner exited')),patch.object(s,'_stop_owned') as cleanup:
        assert not s.start()
        assert s.state=='UNAVAILABLE'
        cleanup.assert_called_once()

def test_reset_ignores_non_inference_and_other_users():
    def proc(name,user):
        p=Mock()
        p.info={'name':name,'username':user}
        return p
    ollama=proc('ollama.exe','me')
    llama=proc('llama-server.exe','me')
    python=proc('python.exe','me')
    other=proc('ollama.exe','other')
    with patch('inference_supervisor.psutil.Process') as current,patch('inference_supervisor.psutil.process_iter',return_value=[ollama,llama,python,other]),patch('inference_supervisor.psutil.wait_procs',return_value=([],[])):
        current.return_value.username.return_value='me'
        assert reset_inference_processes()==2
    ollama.terminate.assert_called_once()
    llama.terminate.assert_called_once()
    python.terminate.assert_not_called()
    other.terminate.assert_not_called()

def test_timeout_does_not_trigger_restart():
    from inference_backend import InferenceTimeout,BackendUnavailable
    s=InferenceSupervisor()
    s.state='READY'
    with patch.object(s,'_json') as health:
        s.report_failure(InferenceTimeout('slow'))
        health.assert_not_called()
        s.report_failure(BackendUnavailable('HTTP error'))
        health.assert_called_once()
        assert not s.recovery_requested.is_set()
    with patch.object(s,'_json',side_effect=OSError('offline')):
        s.report_failure(BackendUnavailable('offline'))
    assert s.recovery_requested.is_set() and s.state=='UNAVAILABLE'
