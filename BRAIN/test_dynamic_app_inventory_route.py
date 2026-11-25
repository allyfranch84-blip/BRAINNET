"""Dynamic application launch contracts; no registry writes or process launch."""
import threading
import time
from unittest.mock import Mock, patch

from causal_trajectory import DynamicAppInventory
from execution_authority import authorization_scope
from ui_motor_context import open_application


def test_inventory_exact_never_falls_back_to_similarity():
    inventory=DynamicAppInventory()
    with patch.object(DynamicAppInventory,'refresh_inventory',return_value={
        'visual studio code':{'tipo':'LNK','cmd':'C:/Programs/Code.lnk'},
        'visual studio':{'tipo':'LNK','cmd':'C:/Programs/VS.lnk'},
    }):
        assert inventory.resolve_exact('Visual Studio Code') == {'tipo':'LNK','cmd':'C:/Programs/Code.lnk'}
        assert inventory.resolve_exact('visual') is None


def test_dynamic_route_blocks_non_enumerated_target_without_launching():
    with authorization_scope(threading.Event()), \
         patch('causal_trajectory.DynamicAppInventory.resolve_exact',return_value=None), \
         patch('ui_motor_context.subprocess.Popen') as popen:
        result=open_application('Visual Studio Code',deadline=time.monotonic()+1)
    assert result['code']=='APP_NOT_ENUMERATED' and result['dispatched'] is False
    popen.assert_not_called()


def test_dynamic_route_never_accepts_protocol_or_command_entries():
    with authorization_scope(threading.Event()), \
         patch('causal_trajectory.DynamicAppInventory.resolve_exact',return_value={'tipo':'PROTOCOL_OR_EXE','cmd':'cmd.exe'}), \
         patch('ui_motor_context.subprocess.Popen') as popen:
        result=open_application('cmd',deadline=time.monotonic()+1)
    assert result['code']=='APP_NOT_ENUMERATED' and result['dispatched'] is False
    popen.assert_not_called()


def test_dynamic_enumerated_shortcut_resolves_to_argument_free_executable():
    # The deadline is deliberately crossed immediately after launch so this
    # test proves the launch contract without waiting for or opening a window.
    with authorization_scope(threading.Event()), \
         patch('causal_trajectory.DynamicAppInventory.resolve_exact',return_value={'tipo':'LNK','cmd':'C:/Programs/Code.lnk'}), \
         patch('ui_motor_context.os.path.isfile',return_value=True), \
         patch('ui_motor_context.os.path.isabs',return_value=True), \
         patch('ui_motor_context._shortcut_target',return_value=('C:/Programs/Code.exe','')) as resolved, \
         patch('ui_motor_context.subprocess.Popen') as popen, \
         patch('win32gui.EnumWindows',side_effect=lambda *_: None), \
         patch('ui_motor_context.time.monotonic',side_effect=[0.0,0.0,2.0]):
        result=open_application('Visual Studio Code',deadline=1.0)
    assert result == {'status':'GOAL_UNVERIFIED','code':'APP_WINDOW_UNCONFIRMED','dispatched':True}
    resolved.assert_called_once_with('C:/Programs/Code.lnk')
    popen.assert_called_once_with(['C:/Programs/Code.exe'],shell=False)


def test_dynamic_shortcut_with_arguments_is_blocked_without_dispatch():
    with authorization_scope(threading.Event()), \
         patch('causal_trajectory.DynamicAppInventory.resolve_exact',return_value={'tipo':'LNK','cmd':'C:/Programs/Unsafe.lnk'}), \
         patch('ui_motor_context.os.path.isfile',return_value=True), \
         patch('ui_motor_context._shortcut_target',return_value=('C:/Programs/Unsafe.exe','--silent')) as resolved, \
         patch('ui_motor_context.subprocess.Popen') as popen:
        result=open_application('Unsafe',deadline=time.monotonic()+1)
    assert result['code']=='APP_SHORTCUT_ARGUMENTS_BLOCKED' and result['dispatched'] is False
    resolved.assert_called_once_with('C:/Programs/Unsafe.lnk')
    popen.assert_not_called()


def test_dynamic_open_binds_only_the_inventoried_process_image():
    browser = Mock()
    browser.name.return_value = 'msedge.exe'
    browser.exe.return_value = 'C:/Browser/msedge.exe'
    app = Mock()
    app.name.return_value = 'Discord.exe'
    app.exe.return_value = 'C:/Apps/Discord.exe'
    app.create_time.return_value = 30
    with authorization_scope(threading.Event()), \
         patch('causal_trajectory.DynamicAppInventory.resolve_exact',
               return_value={'tipo': 'PATH', 'cmd': 'C:/Apps/Discord.exe'}), \
         patch('ui_motor_context.os.path.isfile', return_value=True), \
         patch('win32gui.EnumWindows', side_effect=lambda visit, param: [visit(1, param), visit(2, param)]), \
         patch('win32gui.IsWindowVisible', return_value=True), \
         patch('win32gui.GetWindowText', return_value='Discord'), \
         patch('win32gui.GetForegroundWindow', return_value=1), \
         patch('win32process.GetWindowThreadProcessId', side_effect=lambda hwnd: (0, hwnd + 100)), \
         patch('psutil.Process', side_effect=[browser, app]), \
         patch('uia_chat_readonly.inspect_window', return_value={'hwnd': 2, 'pid': 102, 'started': 30}) as inspect, \
         patch('ui_motor_context.subprocess.Popen') as popen:
        result = open_application('Discord', deadline=time.monotonic() + 5)
    assert result['status'] == 'EFFECT_VERIFIED'
    assert result['window']['hwnd'] == 2
    assert result['focused'] is False and result['dispatched'] is False
    inspect.assert_called_once_with(2)
    popen.assert_not_called()


def test_inventory_shortcut_cannot_launch_an_intermediate_command_host():
    from ui_motor_context import dynamic_launch_path

    with patch('ui_motor_context.os.path.isfile', return_value=True), \
         patch('ui_motor_context._shortcut_target', return_value=('C:/Windows/System32/cmd.exe', '')):
        _, code = dynamic_launch_path({'tipo': 'LNK', 'cmd': 'C:/Apps/Discord.lnk'})
    assert code == 'APP_COMMAND_HOST_BLOCKED'
