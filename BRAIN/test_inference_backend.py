"""Testes simulados do adaptador de inferencia; sem servidor, GPU ou modelo real."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import Mock, patch

from inference_backend import (
    BackendUnavailable, ConfigurationError, HTTPInferenceBackend, InferenceCancelled,
    InferenceRequest, InferenceTimeout, InvalidResponse, LlamaProcessManager,
    ModelUnavailable, ProcessFailed, UnsupportedOperation, create_backend, validate_model_artifacts,
)


class Response:
    def __init__(self, data=b'', lines=(), status=200):
        self.data, self.lines, self.status = data, iter(lines), status
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.data
    def readline(self): return next(self.lines, b'')


class FakeProcess:
    def __init__(self):
        self.returncode, self.stdout, self.terminated, self.killed = None, io.StringIO('startup\n'), False, False
        self.pid = 12345
    def poll(self): return self.returncode
    def terminate(self): self.terminated = True; self.returncode = 0
    def kill(self): self.killed = True; self.returncode = -9
    def wait(self, timeout=None): return self.returncode


class TestInferenceBackend(unittest.TestCase):
    def make(self, opener): return HTTPInferenceBackend('http://127.0.0.1:8080', 'test-model', 'llamacpp', opener=opener)

    def test_unavailable(self):
        def opener(*a, **k): raise URLError(ConnectionRefusedError('offline'))
        with self.assertRaises(BackendUnavailable): self.make(opener).generate(InferenceRequest(prompt='x'))

    def test_invalid_endpoint(self):
        for endpoint in ['file:///x', 'http://example.com:8080', 'http://127.0.0.1:abc', 'http://user:pass@localhost']:
            with self.subTest(endpoint=endpoint), self.assertRaises(ConfigurationError): self.make_for_endpoint(endpoint)

    @staticmethod
    def make_for_endpoint(endpoint): return HTTPInferenceBackend(endpoint, 'model', 'llamacpp')

    def test_complete_response(self):
        opener = Mock(return_value=Response(json.dumps({'content': 'ola'}).encode()))
        result = self.make(opener).generate(InferenceRequest(prompt='oi', request_id='one'))
        self.assertEqual((result.text, result.request_id, result.backend), ('ola', 'one', 'llamacpp'))
        self.assertEqual(json.loads(opener.call_args.args[0].data)['prompt'], 'oi')

    def test_chat_complete(self):
        opener = Mock(return_value=Response(json.dumps({'choices':[{'message':{'content':'ola'}}]}).encode()))
        self.assertEqual(self.make(opener).chat(InferenceRequest(messages=[{'role':'user','content':'oi'}])).text, 'ola')

    def test_llama_chat_explicitly_requests_json_format(self):
        opener = Mock(return_value=Response(
            json.dumps({"choices": [{"message": {"content": '{"intent_type":"none"}'}}]}).encode()
        ))
        backend = self.make(opener)
        messages = [{"role": "user", "content": "Não abra o Paint."}]

        structured = backend.chat(InferenceRequest(messages=messages, json_output=True))
        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(json.loads(structured.text), {"intent_type": "none"})

        backend.chat(InferenceRequest(messages=messages))
        payload = json.loads(opener.call_args.args[0].data)
        self.assertNotIn("response_format", payload)
        self.assertNotIn("temperature", payload)

    def test_ollama_full_and_stream(self):
        opener = Mock(return_value=Response(json.dumps({'response': 'ola', 'done': True}).encode()))
        backend = HTTPInferenceBackend('http://127.0.0.1:11435', 'm', 'ollama', opener=opener)
        self.assertEqual(backend.generate(InferenceRequest(prompt='oi')).text, 'ola')
        opener.return_value = Response(lines=[b'{"response":"o","done":false}\n', b'{"response":"i","done":true}\n'])
        self.assertEqual(''.join(backend.stream(InferenceRequest(prompt='oi'))), 'oi')

    def test_health_check(self):
        backend = self.make(Mock(return_value=Response(status=200)))
        self.assertTrue(backend.health_check())

    def test_404_unknown_endpoint_is_not_model_error(self):
        from urllib.error import HTTPError
        def opener(*a, **k): raise HTTPError('http://localhost',404,'missing',{},io.BytesIO(b'not found'))
        with self.assertRaises(BackendUnavailable): self.make(opener).generate(InferenceRequest(prompt='x'))

    def test_streaming(self):
        lines=[b'data: {"choices":[{"delta":{"content":"o"},"finish_reason":null}]}\n', b'data: {"choices":[{"delta":{"content":"i"},"finish_reason":null}]}\n', b'data: [DONE]\n']
        backend=self.make(Mock(return_value=Response(lines=lines)))
        self.assertEqual(''.join(backend.stream(InferenceRequest(messages=[{'role':'user','content':'oi'}]),chat=True)), 'oi')

    def test_cancel(self):
        lines=[b'data: {"content":"a","stop":false}\n', b'data: {"content":"b","stop":true}\n']
        backend=self.make(Mock(return_value=Response(lines=lines)))
        iterator=backend.stream(InferenceRequest(prompt='x',request_id='cancel-me'))
        self.assertEqual(next(iterator),'a')
        self.assertTrue(backend.cancel('cancel-me'))
        with self.assertRaises(InferenceCancelled): next(iterator)
        self.assertFalse(backend.cancel('cancel-me'))

    def test_timeout(self):
        def opener(*a, **k): raise URLError(TimeoutError('timeout'))
        with self.assertRaises(InferenceTimeout): self.make(opener).generate(InferenceRequest(prompt='x'))

    def test_incomplete_stream(self):
        backend=self.make(Mock(return_value=Response(lines=[b'data: {"content":"a","stop":false}\n'])))
        with self.assertRaises(InvalidResponse): list(backend.stream(InferenceRequest(prompt='x')))

    def test_model_unavailable(self):
        from urllib.error import HTTPError
        def opener(*a, **k): raise HTTPError('http://localhost',404,'missing',{},io.BytesIO(b'{"error":"model not found"}'))
        with self.assertRaises(ModelUnavailable): self.make(opener).generate(InferenceRequest(prompt='x'))

    def test_wrong_local_model_is_rejected(self):
        opener = Mock()
        with self.assertRaises(ModelUnavailable):
            self.make(opener).generate(InferenceRequest(prompt='x', model='another'))
        opener.assert_not_called()

    def test_backend_selection_and_unsupported(self):
        self.assertEqual(create_backend().kind,'ollama')
        self.assertEqual(create_backend({'backend':'llamacpp'}).kind,'llamacpp')
        with self.assertRaises(ConfigurationError): create_backend({'backend':'invalid'})
        with self.assertRaises(UnsupportedOperation): self.make(Mock()).vision(InferenceRequest())
        with self.assertRaises(UnsupportedOperation): self.make(Mock()).embed(InferenceRequest())

    def test_missing_executable_is_configuration_error(self):
        manager=LlamaProcessManager(None,None,probe=lambda:False,port_probe=lambda *a:False)
        with self.assertRaises(ConfigurationError): manager.start()

    def test_existing_external_process_not_stopped(self):
        manager=LlamaProcessManager(None,None,probe=lambda:True)
        self.assertEqual(manager.start(),'external')
        self.assertFalse(manager.stop())

    def test_crash_and_controlled_recovery(self):
        with patch.object(Path, 'is_file', return_value=True), patch('inference_backend.validate_model_artifacts'):
            executable=Path('llama-server.exe')
            model=Path('small.gguf')
            processes=[FakeProcess(),FakeProcess()]
            popen=Mock(side_effect=processes)
            manager=LlamaProcessManager(str(executable),str(model),probe=lambda:False,port_probe=lambda *a:False,popen=popen,max_starts=2,recovery_interval=0)
            self.assertEqual(manager.start(),'started')
            processes[0].returncode=23
            with self.assertRaisesRegex(ProcessFailed,'23'): manager.raise_if_failed('r')
            self.assertEqual(manager.start(),'started')
            processes[1].returncode=24
            with self.assertRaises(ProcessFailed): manager.start()
            self.assertEqual(popen.call_count,2)
            self.assertTrue(manager.stop())

    def test_kernel_not_imported_or_started_by_factory(self):
        import sys
        before=sys.modules.get('BRAINNET')
        create_backend({'backend':'llamacpp'})
        self.assertIs(sys.modules.get('BRAINNET'), before)


class TestSupervisorAddendum(unittest.TestCase):
    def manager(self, processes, **kwargs):
        popen = Mock(side_effect=processes)
        manager = LlamaProcessManager('independent/llama-server.exe', 'small.gguf',
            probe=lambda: False, port_probe=lambda *args: False, popen=popen, **kwargs)
        checker = patch('inference_backend.validate_model_artifacts')
        checker.start()
        self.addCleanup(checker.stop)
        return manager, popen

    @patch.object(Path, 'is_file', return_value=True)
    def test_repeated_crashes_degraded_with_history(self, _):
        processes = [FakeProcess(), FakeProcess()]
        manager, popen = self.manager(processes, max_starts=2, recovery_interval=0, version='test')
        manager.start()
        processes[0].returncode = 10
        self.assertEqual(manager.status()['state'], 'crashed')
        manager.start()
        processes[1].returncode = 11
        with self.assertRaises(ProcessFailed): manager.start()
        status = manager.status()
        self.assertEqual((status['state'], status['exit_code'], status['reason']), ('degraded', 11, 'restart_limit'))
        self.assertEqual((status['pid'], status['version'], status['backend']), (12345, 'test', 'llamacpp'))
        self.assertEqual(popen.call_count, 2)
        self.assertTrue(any(e['event'] == 'process_exit' for e in status['events']))

    def test_port_occupied_does_not_start_or_kill(self):
        manager = LlamaProcessManager(None, None, probe=lambda: False, port_probe=lambda *a: True, popen=Mock())
        with self.assertRaises(BackendUnavailable): manager.start()
        self.assertEqual(manager.status()['reason'], 'port_occupied')
        manager._popen.assert_not_called()
        self.assertFalse(manager.stop())

    @patch.object(Path, 'is_file', return_value=False)
    def test_missing_model_has_specific_error(self, _):
        with patch.object(Path, 'is_file', side_effect=[True, False]):
            manager, popen = self.manager([], recovery_interval=0)
            with self.assertRaises(ModelUnavailable): manager.start()
            popen.assert_not_called()

    @patch.object(Path, 'is_file', return_value=True)
    def test_vulkan_startup_exit_is_recorded(self, _):
        p = FakeProcess()
        manager, _ = self.manager([p], device='vulkan', max_starts=1)
        manager.start()
        manager._recent.append('Vulkan initialization failed')
        p.returncode = 7
        status = manager.status()
        self.assertEqual(status['reason'], 'vulkan_error_reported')
        self.assertEqual(status['exit_code'], 7)
        self.assertEqual(status['state'], 'degraded')

    @patch.object(Path, 'is_file', return_value=True)
    def test_transient_failure_waits_then_recovers(self, _):
        now = [100.0]
        p1, p2 = FakeProcess(), FakeProcess()
        manager, popen = self.manager([p1, p2], clock=lambda: now[0], recovery_interval=5)
        manager.start()
        p1.returncode = 1
        with self.assertRaises(ProcessFailed): manager.start()
        self.assertEqual(manager.status()['state'], 'recovery_wait')
        self.assertEqual(popen.call_count, 1)
        now[0] += 5
        self.assertEqual(manager.start(), 'started')
        self.assertEqual(popen.call_count, 2)

    def test_ports_and_ollama_executable_forbidden(self):
        for port in (11434, 11435):
            with self.subTest(port=port), self.assertRaises(ConfigurationError):
                LlamaProcessManager(None, None, endpoint=f'http://127.0.0.1:{port}')
            with self.assertRaises(ConfigurationError):
                create_backend({'backend':'llamacpp', 'endpoint':f'http://127.0.0.1:{port}'})
        import os
        path = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'lib' / 'ollama' / 'llama-server.exe'
        manager = LlamaProcessManager(str(path), 'model.gguf', probe=lambda:False, port_probe=lambda *a:False)
        with patch.object(Path, 'is_file', return_value=True), self.assertRaises(ConfigurationError):
            manager.start()

    def test_artifacts_checked_separately(self):
        with patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'open', side_effect=lambda *args, **kwargs: io.BytesIO(b'GGUFfake')):
            with self.assertRaises(ConfigurationError): validate_model_artifacts('m.gguf', require_vision=True)
            with self.assertRaises(ConfigurationError): validate_model_artifacts('m.gguf', require_template=True)
            result = validate_model_artifacts('m.gguf', 'mmproj.gguf', require_vision=True)
            self.assertFalse(result['compatibility_verified'])
            self.assertEqual(result['projector'], 'mmproj.gguf')
            with patch.object(Path, 'read_text', return_value='{{ messages }}'):
                result = validate_model_artifacts('m.gguf', 'mmproj.gguf', 'chat.jinja', require_vision=True, require_template=True)
                self.assertTrue(result['template_present'])

    def test_requested_shutdown_recorded(self):
        p = FakeProcess()
        manager, _ = self.manager([p], recovery_interval=0)
        with patch.object(Path, 'is_file', return_value=True): manager.start()
        self.assertTrue(manager.stop())
        self.assertEqual(manager.status()['reason'], 'requested_shutdown')
        self.assertTrue(p.terminated)
        events = [e['event'] for e in manager.status()['events']]
        self.assertIn('STOP_REQUESTED', events)
        self.assertIn('FORCED_TERMINATION', events)
        self.assertNotIn('STOPPED_GRACEFULLY', events)
        self.assertNotIn('PROCESS_FAILED', events)

    @patch.object(Path, 'is_file', return_value=True)
    def test_unexpected_exit_recorded_as_process_failed(self, _):
        p = FakeProcess()
        manager, _ = self.manager([p], recovery_interval=0)
        manager.start()
        p.returncode = 1
        events = [e['event'] for e in manager.status()['events']]
        self.assertIn('PROCESS_FAILED', events)
        self.assertNotIn('STOP_REQUESTED', events)

    def test_absent_gpu_counter_is_unknown(self):
        import importlib.util
        script = Path(__file__).resolve().parent.parent / 'llama_cpp_independent' / 'b12255' / 'benchmark_003c1.py'
        spec = importlib.util.spec_from_file_location('benchmark_003c1', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.subprocess, 'run', return_value=Mock(returncode=0, stdout='')):
            self.assertEqual(module.gpu_memory(123), 'UNKNOWN')


if __name__ == '__main__': unittest.main()
