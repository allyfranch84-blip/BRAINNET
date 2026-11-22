"""Protocol, escala e travas factuais; nenhum teste injeta input real no SO."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
import pytest

from actuator_bridge import ActuatorBridge
from ui_tars_protocol import UIProtocolController, parse_ui_action, protocol_to_dispatch
from vision_eye import RealVisionEngine


def test_native_and_json_envelopes():
    native = parse_ui_action("Thought: Botao visivel\nAction: click(start_box='(10,20)')")
    envelope = parse_ui_action(json.dumps({"thought": "Botao visivel", "action": "click(start_box='(10,20)')"}))
    assert native == envelope
    assert native["action_inputs"]["start_box"] == [10, 20]


@pytest.mark.parametrize("response", [
    "Action: __import__('os').system('whoami')", "Action: x.click(start_box='(1,2)')",
    "Action: click(start_box=str(1))", "Action: click(**{})", "Action: click(start_box='(1,2)',extra='x')",
    "Action: click(start_box='(-1,2)')", "Action: click(start_box='(True,2)')",
    "Action: click(start_box='(9,8,1,2)')", "Action: hotkey(key='win r')",
    "Action: hotkey(key='ctrl ctrl')", "Action: type(content='line1\\nline2')",
    "Action: wait(); click(start_box='(1,2)')",
])
def test_rejects_untrusted_or_unsupported_actions(response):
    with pytest.raises((ValueError, SyntaxError)):
        parse_ui_action(response)


def test_scaling_negative_monitor_origin_and_bounds():
    assert RealVisionEngine.protocol_point_to_screen([50, 25], (100, 50), (-200, 100, 0, 200)) == (-100, 150)
    with pytest.raises(ValueError):
        RealVisionEngine.protocol_point_to_screen([100, 25], (100, 50), (0, 0, 200, 100))


def test_translation_uses_atomic_click_and_literal_text():
    action = parse_ui_action("Action: left_double(start_box='(10,20)')")
    command, payload = protocol_to_dispatch(action, RealVisionEngine(), (100, 100), (0, 0, 200, 200))
    assert command == "mouse_click_at" and payload == {"x": 20, "y": 40, "button": "left", "count": 2}
    assert protocol_to_dispatch(parse_ui_action("Action: hotkey(key='control l')"), None, None, None) == ("hotkey", {"keys": ["ctrl", "l"]})


def test_bridge_click_moves_then_clicks_under_lock():
    effector = MagicMock()
    effector.mouse_move.return_value = effector.mouse_click.return_value = True
    bridge = ActuatorBridge(effector_instance=effector)
    async def check():
        await bridge.start()
        try:
            result = await bridge.dispatch("mouse_click_at", {"x": 10, "y": 20, "count": 2})
            assert result.status == "completed" and result.result is True
        finally:
            await bridge.stop()
    asyncio.run(check())
    assert [call[0] for call in effector.mock_calls] == ["mouse_move", "mouse_click"]


def test_vision_sends_image_schema_and_unloads_model():
    vision = RealVisionEngine()
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"done": True, "message": {"content": json.dumps({"thought": "editor", "action": "click(start_box='(10,20)')"})}}).encode()
    with patch("vision_eye.urllib.request.urlopen", return_value=response) as request:
        result = vision.describe_ui_with_protocol(Image.new("RGB", (2560, 1440)), "click editor", [])
    payload = json.loads(request.call_args.args[0].data)
    assert payload["model"] == "qwen2.5vl:3b"
    assert payload["keep_alive"] == 0 and payload["format"]["additionalProperties"] is False
    assert payload["messages"][0]["images"]
    assert result["image_size"] == (1280, 720)


def make_controller(actions):
    vision, context = MagicMock(), MagicMock()
    snapshot = {"hwnd": 7, "window_rect": (0, 0, 100, 100), "process_name": "notepad.exe"}
    vision.capture_ui_observation.return_value = (Image.new("RGB", (100, 100)), (0, 0, 100, 100), snapshot)
    vision.describe_ui_with_protocol.side_effect = actions
    context.capture_foreground_context.return_value = snapshot
    trajectory = SimpleNamespace(bridge=SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True, error=None)) ))
    return UIProtocolController(vision, trajectory, context), trajectory


@pytest.mark.parametrize("content", [
    "Vou clicar no editor para voce.",
    "Thought: editor\nAction: click(start_box='(10,20)')",
    '```json\n{"thought":"editor","action":"wait()"}\n```',
    '{"thought":"editor","action":"wait()"}\ntexto extra',
])
def test_fallback_rejects_conversational_or_non_json_responses(content):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"done": True, "message": {"content": content}}).encode()
    with patch("vision_eye.urllib.request.urlopen", return_value=response):
        with pytest.raises(ValueError):
            RealVisionEngine().describe_ui_with_protocol(Image.new("RGB", (100, 100)), "digite teste", [])


def test_kernel_bridge_passes_direct_instruction_without_browser_url():
    from BRAINNET import BrainnetBridge
    from theory_of_mind import MotorGateState
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = MagicMock()
    bridge._kernel.loop = None
    bridge._kernel.ui_protocol.run_task = AsyncMock(return_value={"status": "AWAITING_GOAL_VERIFICATION"})
    bridge._tom = MagicMock()
    bridge._tom.evaluate_intent.return_value = SimpleNamespace(gate=MotorGateState.GO)
    task = "no Brave pesquise 'python'"
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("URL nao deve ser consultada")):
        result = bridge._executar_comando_interno(f"/ui {task}", f"/ui {task}".lower(), f"/ui {task}".lower())
    bridge._kernel.ui_protocol.run_task.assert_awaited_once_with(task)
    assert "AWAITING_GOAL_VERIFICATION" in result["reply"]


def test_failed_ncd_stops_before_next_action():
    action = {**parse_ui_action("Action: type(content='teste')"), "image_size": (100, 100)}
    controller, trajectory = make_controller([action])
    async def measure(**kwargs):
        assert kwargs["contract"]["action"] == "TYPE"
        assert kwargs["contract"]["expects_new_pid"] is False
        assert kwargs["contract"]["min_ncd"] == 0.02
        await kwargs["action_fn"]()
        return {"lambda_obs": 0, "ncd_real": 0.01, "expected_delta": 0.03}
    trajectory.execute_subgoal = AsyncMock(side_effect=measure)
    result = asyncio.run(controller.run_task("digite teste"))
    assert result["status"] == "FAILED_FACTUAL" and result["sucesso_real"] is False
    trajectory.bridge.dispatch.assert_awaited_once_with("send_text", {"text": "teste"})


def test_finished_without_verified_action_never_claims_success():
    controller, trajectory = make_controller([parse_ui_action("Action: finished(content='done')")])
    trajectory.execute_subgoal = AsyncMock()
    result = asyncio.run(controller.run_task("digite teste", goal_check=lambda: True))
    assert result["status"] == "AWAITING_GOAL_VERIFICATION"
    trajectory.execute_subgoal.assert_not_awaited()


def test_focus_change_blocks_input_before_actuation():
    action = {**parse_ui_action("Action: type(content='teste')"), "image_size": (100, 100)}
    controller, trajectory = make_controller([action])
    controller.context_engine.capture_foreground_context.return_value = {"hwnd": 99}
    async def measure(**kwargs):
        with pytest.raises(RuntimeError, match="Foco/geometria"):
            await kwargs["action_fn"]()
        return {"lambda_obs": 0}
    trajectory.execute_subgoal = AsyncMock(side_effect=measure)
    assert asyncio.run(controller.run_task("digite teste"))["status"] == "FAILED_FACTUAL"
    trajectory.bridge.dispatch.assert_not_awaited()


class TestMission002Contract(__import__('unittest').TestCase):
    """Contrato visual sem hardware, rede, GPU ou processos externos."""

    def setUp(self):
        import threading
        from execution_authority import authorization_scope
        self.token = threading.Event()
        self.scope = authorization_scope(self.token)
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.addCleanup(self.token.set)

    def test_drag_routes_to_effector(self):
        actuator = MagicMock()
        actuator.mouse_drag.return_value = True
        bridge = ActuatorBridge(effector_instance=actuator)
        result = asyncio.run(bridge._route_execution('mouse_drag', {'x1': 1, 'y1': 2, 'x2': 30, 'y2': 40}))
        self.assertIs(result, True)
        actuator.mouse_drag.assert_called_once_with(1, 2, 30, 40)

    def test_invalid_drag_is_rejected_before_dispatch(self):
        action = parse_ui_action("Action: drag(start_box='(1,2)', end_box='(1,2)')")
        with self.assertRaises(ValueError):
            protocol_to_dispatch(action, RealVisionEngine(), (100, 100), (0, 0, 100, 100))
        with self.assertRaises(ValueError):
            parse_ui_action("Action: drag(start_box='(x,y)', end_box='(1,2)')")

    def test_drag_releases_button_on_failure(self):
        import ctypes
        import effector as mouse
        events = []
        def send(count, ptr, size):
            events.append(ctypes.cast(ptr, ctypes.POINTER(mouse.INPUT)).contents.u.mi.dwFlags)
            return 1
        with patch('effector.user32', SimpleNamespace(SendInput=send)), patch.object(mouse.Effector, 'mouse_move', side_effect=[True, RuntimeError('simulated')]):
            with self.assertRaisesRegex(RuntimeError, 'simulated'):
                mouse.Effector().mouse_drag(1, 2, 3, 4)
        self.assertEqual(events, [mouse.MOUSEEVENTF_LEFTDOWN, mouse.MOUSEEVENTF_LEFTUP])

    def test_scroll_protocol(self):
        action = parse_ui_action("Action: scroll(direction='down', clicks=2)")
        self.assertEqual(protocol_to_dispatch(action, None, None, None), ('scroll', {'direction': 'down', 'clicks': 2}))
        with self.assertRaises(ValueError):
            parse_ui_action("Action: scroll(direction='left', clicks=1)")

    def test_rejects_untrusted_text(self):
        with self.assertRaises((ValueError, SyntaxError)):
            parse_ui_action("Action: __import__('os').system('echo unsafe')")
        with self.assertRaises(ValueError):
            parse_ui_action("Action: click on the circle")

    def test_high_ncd_does_not_confirm_goal(self):
        actions = [{**parse_ui_action("Action: click(start_box='(10,20)')"), 'image_size': (100, 100)}, parse_ui_action("Action: finished(content='done')")]
        controller, trajectory = make_controller(actions)
        controller.vision.protocol_point_to_screen.return_value = (10, 20)
        async def measure(**kwargs):
            await kwargs['action_fn']()
            return {'lambda_obs': 1, 'ncd_real': .99}
        trajectory.execute_subgoal = AsyncMock(side_effect=measure)
        result = asyncio.run(controller.run_task('draw'))
        self.assertFalse(result['sucesso_real'])
        self.assertEqual(result['goal_state'], 'GOAL_UNVERIFIED')
        self.assertEqual(result['trace'][0]['action_state'], 'ACTION_OBSERVED')

    def test_finished_without_goal_check(self):
        controller, trajectory = make_controller([parse_ui_action("Action: finished(content='done')")])
        result = asyncio.run(controller.run_task('draw'))
        self.assertFalse(result['sucesso_real'])
        self.assertEqual(result['goal_state'], 'GOAL_UNVERIFIED')

    def test_existing_protocol_formats(self):
        a = parse_ui_action("Thought: ok\nAction: click(start_box='(10,20)')")
        b = parse_ui_action(json.dumps({'thought': 'ok', 'action': "click(start_box='(10,20)')"}))
        self.assertEqual(a, b)
        self.assertEqual(protocol_to_dispatch(parse_ui_action("Action: hotkey(key='control l')"), None, None, None), ('hotkey', {'keys': ['ctrl', 'l']}))

    def test_trajectory_drag_validates_window_before_dispatch(self):
        from causal_trajectory import CausalTrajectoryEngine
        engine = object.__new__(CausalTrajectoryEngine)
        engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status='completed', result=True)))
        engine.ctx_engine = SimpleNamespace(capture_foreground_context=lambda: {'hwnd': 7, 'window_rect': (0, 0, 100, 100)})
        step = {'acao': 'DRAG', 'x1': 1, 'y1': 2, 'x2': 50, 'y2': 60}
        self.assertTrue(asyncio.run(engine._executar_passo_individual(step)))
        engine.bridge.dispatch.assert_awaited_once()
        engine.bridge.dispatch.reset_mock()
        with self.assertRaises(ValueError):
            asyncio.run(engine._executar_passo_individual(dict(step, x2=101)))
        engine.bridge.dispatch.assert_not_awaited()

    def test_confirmed_goal_requires_callback_and_observed_action(self):
        actions = [{**parse_ui_action("Action: click(start_box='(10,20)')"), 'image_size': (100, 100)}, parse_ui_action("Action: finished(content='done')")]
        controller, trajectory = make_controller(actions)
        controller.vision.protocol_point_to_screen.return_value = (10, 20)
        async def measure(**kwargs):
            await kwargs['action_fn']()
            return {'lambda_obs': 1, 'verification_ms': 1.0}
        trajectory.execute_subgoal = AsyncMock(side_effect=measure)
        result = asyncio.run(controller.run_task('draw', goal_check=lambda: True))
        self.assertTrue(result['sucesso_real'])
        self.assertEqual(result['goal_state'], 'GOAL_VERIFIED')
        self.assertIn('task_id', result)
        self.assertEqual(result['trace'][0]['execution_state'], 'ACTION_EXECUTED')
        self.assertIn('capture_ms', result['trace'][0]['timings_ms'])
        self.assertEqual(result['trace'][0]['timings_ms']['verification_ms'], 1.0)

    def test_scroll_dispatch_in_controller(self):
        action = {**parse_ui_action("Action: scroll(direction='up', clicks='2')"), 'image_size': (100, 100)}
        controller, trajectory = make_controller([action, parse_ui_action("Action: finished(content='done')")])
        async def measure(**kwargs):
            self.assertEqual(kwargs['contract']['action'], 'SCROLL')
            await kwargs['action_fn']()
            return {'lambda_obs': 1}
        trajectory.execute_subgoal = AsyncMock(side_effect=measure)
        result = asyncio.run(controller.run_task('scroll'))
        trajectory.bridge.dispatch.assert_awaited_once_with('scroll', {'direction': 'up', 'clicks': 2})
        self.assertEqual(result['goal_state'], 'GOAL_UNVERIFIED')

    def test_trajectory_drag_primitive_alias(self):
        from causal_trajectory import CausalTrajectoryEngine
        engine = object.__new__(CausalTrajectoryEngine)
        engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status='completed', result=True)))
        engine.ctx_engine = SimpleNamespace(capture_foreground_context=lambda: {'hwnd': 7, 'window_rect': (0, 0, 100, 100)})
        self.assertTrue(asyncio.run(engine._executar_passo_individual({'p': 'DRAG', 'x1': 1, 'y1': 2, 'x2': 30, 'y2': 40})))
        engine.bridge.dispatch.assert_awaited_once()


class TestMission0021VisualGoal(__import__('unittest').TestCase):
    def setUp(self):
        import threading
        from execution_authority import authorization_scope
        self.token = threading.Event()
        self.scope = authorization_scope(self.token)
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.addCleanup(self.token.set)
        from PIL import ImageDraw
        self.draw = ImageDraw
        self.before = Image.new('RGB', (160, 160), 'white')
        self.roi = (20, 20, 140, 140)

    def check_shape(self, shape, color, width=0, before=None):
        from visual_goal_verifier import verify_new_red_circle
        before = before or self.before
        after = before.copy()
        d = self.draw.Draw(after)
        kwargs = {'outline': color, 'width': width} if width else {'fill': color}
        getattr(d, shape)((40, 40, 110, 110), **kwargs)
        return verify_new_red_circle(before, after, self.roi)

    def test_filled_red_circle(self): self.assertTrue(self.check_shape('ellipse', 'red'))
    def test_red_rectangle_rejected(self): self.assertFalse(self.check_shape('rectangle', 'red'))
    def test_blue_circle_rejected(self): self.assertFalse(self.check_shape('ellipse', 'blue'))
    def test_red_outline_circle(self): self.assertTrue(self.check_shape('ellipse', 'red', width=3))
    def test_existing_red_circle_not_counted(self):
        from visual_goal_verifier import verify_new_red_circle
        before=self.before.copy()
        self.draw.Draw(before).ellipse((40,40,110,110), fill='red')
        self.assertFalse(verify_new_red_circle(before, before.copy(), self.roi))
    def test_new_red_circle_with_existing_red_element(self):
        before=self.before.copy()
        self.draw.Draw(before).rectangle((22,22,28,28), fill='red')
        self.assertTrue(self.check_shape('ellipse', 'red', before=before))
    def test_change_outside_canvas_rejected(self):
        from visual_goal_verifier import verify_new_red_circle
        after=self.before.copy()
        self.draw.Draw(after).ellipse((0,0,15,15),fill='red')
        self.assertFalse(verify_new_red_circle(self.before, after, self.roi))
    def test_unknown_canvas_rejected(self):
        from visual_goal_verifier import verify_new_red_circle
        after=self.before.copy()
        self.draw.Draw(after).ellipse((40,40,110,110),fill='red')
        self.assertFalse(verify_new_red_circle(self.before, after, None))
    def test_scroll_prompt_matches_parser(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'done': True, 'message': {'content': json.dumps({'thought': 'ok', 'action': "scroll(direction='down', clicks=2)"})}}).encode()
        with patch('vision_eye.urllib.request.urlopen', return_value=response) as request:
            result=RealVisionEngine().describe_ui_with_protocol(self.before,'scroll',[])
        payload=json.loads(request.call_args.args[0].data)
        self.assertIn('scroll(direction=',payload['messages'][0]['content'])
        self.assertEqual(result['action_inputs']['clicks'], 2)

    def test_controller_verifies_explicit_canvas(self):
        before=self.before.copy()
        after=before.copy()
        self.draw.Draw(after).ellipse((40,40,110,110),fill='red')
        action={**parse_ui_action("Action: click(start_box='(30,30)')"),'image_size':(160,160)}
        controller, trajectory=make_controller([action,parse_ui_action("Action: finished(content='done')")])
        context={'hwnd':7,'window_rect':(0,0,160,160),'process_name':'mspaint.exe','verified_canvas_rect':self.roi}
        controller.vision.capture_ui_observation.side_effect=[(before,(0,0,160,160),context),(after,(0,0,160,160),context)]
        controller.context_engine.capture_foreground_context.return_value=context
        controller.vision.protocol_point_to_screen.return_value=(30,30)
        async def measure(**kwargs):
            await kwargs['action_fn']()
            return {'lambda_obs':1}
        trajectory.execute_subgoal=AsyncMock(side_effect=measure)
        result=asyncio.run(controller.run_task('pinte um círculo vermelho'))
        self.assertEqual(result['goal_state'],'GOAL_VERIFIED')

    def test_controller_without_identified_canvas_is_unverified(self):
        before=self.before.copy()
        after=before.copy()
        self.draw.Draw(after).ellipse((40,40,110,110),fill='red')
        action={**parse_ui_action("Action: click(start_box='(30,30)')"),'image_size':(160,160)}
        controller, trajectory=make_controller([action,parse_ui_action("Action: finished(content='done')")])
        context={'hwnd':7,'window_rect':(0,0,160,160),'process_name':'mspaint.exe'}
        controller.vision.capture_ui_observation.side_effect=[(before,(0,0,160,160),context),(after,(0,0,160,160),context)]
        controller.context_engine.capture_foreground_context.return_value=context
        controller.vision.protocol_point_to_screen.return_value=(30,30)
        async def measure(**kwargs):
            await kwargs['action_fn']()
            return {'lambda_obs':1}
        trajectory.execute_subgoal=AsyncMock(side_effect=measure)
        result=asyncio.run(controller.run_task('pinte um círculo vermelho'))
        self.assertEqual(result['goal_state'],'GOAL_UNVERIFIED')
