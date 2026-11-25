"""Supervisor contracts, mocked processes and HTTP only."""
from unittest.mock import Mock,patch
from inference_supervisor import InferenceSupervisor

def test_owned_start_checks_catalog_before_warmup():
    with patch.dict('os.environ',{'BRAINNET_INFERENCE_BACKEND':'ollama','BRAINNET_MOTOR_MODEL':'qwen2.5:1.5b'}):
        s=InferenceSupervisor()
    responses=[{'version':'test'},{'models':[{'name':'qwen2.5:1.5b'}]},{'done':True,'response':'OK'}]
    with patch.object(s,'_port_free',return_value=True),patch.object(s,'_spawn'),patch.object(s,'_alive',return_value=True),patch.object(s,'_json',side_effect=responses) as request:
        assert s.start(reset=True)
        assert request.call_args_list[2].args[0]=='/api/generate'
        assert s.state=='READY'

def test_warmup_failure_not_reported_as_ready():
    s=InferenceSupervisor()
    with patch.object(s,'_port_free',return_value=True),patch.object(s,'_spawn'),patch.object(s,'_warmup',side_effect=RuntimeError('runner exited')),patch.object(s,'_stop_owned') as cleanup:
        assert not s.start()
        assert s.state=='UNAVAILABLE'
        cleanup.assert_called_once()

def test_reset_attaches_existing_server_without_generation_or_process_operations():
    s=InferenceSupervisor()
    catalog=[{'version':'test'},{'models':[{'name':s.model}]}]
    with patch.object(s,'_port_free',return_value=False), patch.object(s,'_json',side_effect=catalog) as http, \
         patch.object(s,'_spawn') as spawn, patch('inference_supervisor.psutil.Process') as process:
        assert s.start(reset=True)
        assert s.status()['ownership']=='external' and s.status()['state']=='AVAILABLE'
        assert s.backend(s.model).model==s.model
        assert [c.args for c in http.call_args_list]==[('/api/version',),('/api/tags',)]
        s.stop()
        spawn.assert_not_called()
        process.assert_not_called()


def test_unknown_listener_never_triggers_spawn():
    s=InferenceSupervisor()
    with patch.object(s,'_port_free',return_value=False),patch.object(s,'_json',return_value={}),patch.object(s,'_spawn') as spawn:
        assert not s.start(reset=True)
        assert s.state=='UNAVAILABLE'
        spawn.assert_not_called()


def test_external_health_loss_never_schedules_process_replacement():
    from inference_backend import BackendUnavailable
    s=InferenceSupervisor()
    s.external=True
    s.state='AVAILABLE'
    with patch.object(s,'_json',side_effect=OSError('offline')):
        s.report_failure(BackendUnavailable('failed'))
    assert s.state=='UNAVAILABLE' and not s.recovery_requested.is_set()


def test_preflight_does_not_generate_for_missing_model_even_if_requested():
    s=InferenceSupervisor()
    with patch.object(s,'_json',side_effect=[{'version':'test'},{'models':[]},{'models':[]}]) as http:
        result=s.preflight(probe=True)
    assert result['selected_installed'] is False and result['inference']=='NOT_TESTED'
    assert all(len(c.args)==1 for c in http.call_args_list)

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
