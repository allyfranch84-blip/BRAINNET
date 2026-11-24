"""Isolated lab helpers. Import does not open a window or move the pointer."""
import time
import os
import ctypes
from ctypes import wintypes
from execution_authority import require_action_allowed


def observe_cursor_monitors(api=None):
    """Read-only Win32 observation; no assertion of DPI or desktop identity."""
    if api is None:
        import win32api as api
    result = {'timestamp': time.time(), 'source': 'Win32 GetCursorPos/EnumDisplayMonitors/MonitorFromPoint/GetMonitorInfo',
              'session_id': None, 'desktop': 'UNKNOWN', 'interactive_desktop_verified': False,
              'dpi': 'UNKNOWN', 'mss_mapping': 'UNKNOWN'}
    if os.name == 'nt':
        session = wintypes.DWORD()
        if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            result['session_id'] = session.value
        try:
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
            user32.GetThreadDesktop.restype = wintypes.HANDLE
            user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            user32.OpenInputDesktop.restype = wintypes.HANDLE
            user32.CloseDesktop.argtypes = [wintypes.HANDLE]
            user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
            thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            thread_desktop = user32.GetThreadDesktop(thread_id)
            input_desktop = user32.OpenInputDesktop(0, False, 1)
            def desktop_name(handle):
                required = wintypes.DWORD()
                user32.GetUserObjectInformationW(handle, 2, None, 0, ctypes.byref(required))
                if not required.value:
                    return None
                buf = ctypes.create_unicode_buffer(required.value // ctypes.sizeof(ctypes.c_wchar) + 1)
                if not user32.GetUserObjectInformationW(handle, 2, buf, ctypes.sizeof(buf), ctypes.byref(required)):
                    return None
                return buf.value
            try:
                current = desktop_name(thread_desktop) if thread_desktop else None
                active = desktop_name(input_desktop) if input_desktop else None
                result['desktop'] = current or 'UNKNOWN'
                result['input_desktop'] = active or 'UNKNOWN'
                result['interactive_desktop_verified'] = bool(current and active and current == active and result['session_id'] not in (None, 0))
            finally:
                if input_desktop:
                    user32.CloseDesktop(input_desktop)
        except (OSError, AttributeError, ValueError):
            pass
    try:
        result['cursor'] = tuple(api.GetCursorPos())
        result['cursor_status'] = 'OK'
    except Exception as exc:
        result.update(cursor=None, cursor_status='ERROR', cursor_error_code=getattr(exc, 'winerror', None),
                      cursor_error_type=type(exc).__name__, monitors=[], cursor_monitor=None)
        return result
    try:
        monitors = []
        for handle, _, _ in api.EnumDisplayMonitors():
            info = api.GetMonitorInfo(handle)
            monitors.append({'handle': int(handle), 'device': info.get('Device'),
                             'monitor_rect': tuple(info['Monitor']), 'work_rect': tuple(info['Work'])})
        handle = api.MonitorFromPoint(result['cursor'], 0)
        result['monitors'] = monitors
        result['cursor_monitor'] = next((m for m in monitors if m['handle'] == int(handle)), None)
        result['monitor_status'] = 'OK' if result['cursor_monitor'] else 'UNAVAILABLE'
    except Exception as exc:
        result.update(monitors=[], cursor_monitor=None, monitor_status='ERROR',
                      monitor_error_code=getattr(exc, 'winerror', None), monitor_error_type=type(exc).__name__)
    return result


def propose_right_30(observation):
    """Return geometry only; screen content and sensitive regions remain unverified."""
    point = observation.get('cursor')
    monitor = observation.get('cursor_monitor')
    if not point or not monitor:
        return {'status': 'INCONCLUSIVE', 'reason': 'Cursor ou monitor indisponível'}
    x, y = point
    left, top, right, bottom = monitor['work_rect']
    target = (x + 30, y)
    inside = left <= x < right and top <= y < bottom and left <= target[0] < right and top <= target[1] < bottom
    return {'status': 'REQUIRES_REVIEW' if inside else 'OUT_OF_BOUNDS', 'start': point,
            'target': target, 'monitor': monitor, 'sensitive_regions_verified': False,
            'desktop_verified': observation.get('interactive_desktop_verified') is True,
            'execution_authorized': False}


def bounded_linear_points(start, dx, dy, safe_rect):
    """Calculate a deterministic, bounded path; does not access the desktop."""
    if (not isinstance(start, (tuple, list)) or len(start) != 2
            or not isinstance(safe_rect, (tuple, list)) or len(safe_rect) != 4
            or any(type(v) is not int for v in (*start, dx, dy, *safe_rect))
            or not 0 < abs(dx) + abs(dy) <= 100):
        raise ValueError('Invalid coordinates or displacement')
    left, top, right, bottom = safe_rect
    if left >= right or top >= bottom:
        raise ValueError('Invalid safe rectangle')
    steps = max(abs(dx), abs(dy))
    points = [(start[0] + round(dx * i / steps), start[1] + round(dy * i / steps))
              for i in range(steps + 1)]
    if not all(left <= x < right and top <= y < bottom for x, y in points):
        raise ValueError('Path leaves safe rectangle')
    return points


def prepare_safe_trajectory(task_id, observation, lab_hwnd, safe_rect, controls_rects,
                            *, dpi_verified=False, lab_verified=False):
    """Prepare only; caller must provide independently observed physical geometry."""
    result = {'task_id': task_id, 'status': 'NOT_READY', 'lab_hwnd': lab_hwnd,
              'authorization': 'NOT_GRANTED', 'executor': 'ActuatorBridge mouse_move',
              'verification': 'independent Win32 GetCursorPos after authorized movement'}
    def valid_rect(rect):
        return (isinstance(rect, (tuple, list)) and len(rect) == 4
                and all(type(v) is int for v in rect) and rect[0] < rect[2] and rect[1] < rect[3])
    if not task_id or not lab_hwnd or not lab_verified:
        result['reason'] = 'Identidade da tarefa ou janela não verificada'
        return result
    if not dpi_verified:
        result['reason'] = 'Espaço físico e DPI do observador e executor não confirmados'
        return result
    if (not valid_rect(safe_rect) or controls_rects is None
            or any(not valid_rect(rect) for rect in controls_rects)):
        result['reason'] = 'Região segura ou controles não observados com confiança'
        return result
    point = observation.get('cursor')
    monitor = observation.get('cursor_monitor')
    if (observation.get('cursor_status') != 'OK' or not observation.get('interactive_desktop_verified')
            or not isinstance(point, (tuple, list)) or len(point) != 2
            or any(type(v) is not int for v in point) or not monitor
            or not valid_rect(monitor.get('work_rect'))):
        result['reason'] = 'Cursor, desktop ou monitor indisponível'
        return result
    x, y = point
    target = (x + 30, y)
    result.update(start=(x, y), target=target, safe_rect=tuple(safe_rect),
                  monitor=monitor, source=observation.get('source'), timestamp=observation.get('timestamp'))
    def contains(rect, p):
        return rect[0] <= p[0] < rect[2] and rect[1] <= p[1] < rect[3]
    if not contains(safe_rect, point):
        result['reason'] = 'Posicione o cursor manualmente dentro da região segura observada'
    elif not all(contains(rect, p) for rect in (safe_rect, monitor['work_rect']) for p in (point, target)):
        result['reason'] = 'Segmento fora da região segura ou da área útil do monitor'
    elif any(rect[1] <= y < rect[3] and x < rect[2] and target[0] >= rect[0] for rect in controls_rects):
        result['reason'] = 'Segmento intercepta controle interativo'
    else:
        result.update(status='AWAITING_AUTHORIZATION', reason='Trajeto proposto; nenhuma atuação autorizada')
    return result


def attach_motor_observation(task, observation):
    """Attach a read-only observation to the existing continuity contract."""
    from adaptive_resource_controller import TaskContinuity
    if not isinstance(task, TaskContinuity):
        raise ValueError('TaskContinuity required')
    if (observation.get('cursor_status') != 'OK' or observation.get('monitor_status') != 'OK'
            or observation.get('interactive_desktop_verified') is not True):
        return False
    task.last_validated_observation = {'type': 'motor_observation', 'source': observation['source'],
        'timestamp': observation['timestamp'], 'cursor': tuple(observation['cursor']),
        'monitor': dict(observation['cursor_monitor']), 'dpi': observation.get('dpi', 'UNKNOWN'),
        'execution_authorized': False}
    return True


async def verify_relative_move(bridge, read_position, bounds, dx, dy):
    """Use existing actuator and an independent sensor; caller supplies authorization."""
    require_action_allowed('MOUSE_MOVE')
    if (not callable(read_position) or not isinstance(bounds, (tuple, list)) or len(bounds)!=4
            or any(type(x) is not int for x in (*bounds, dx, dy)) or abs(dx)+abs(dy)>100
            or (dx == 0 and dy == 0)):
        return {'status':'INCONCLUSIVE','reason':'Invalid sensor, bounds or displacement'}
    try:
        x,y=read_position()
        if type(x) is not int or type(y) is not int:
            raise ValueError('position must use integer screen coordinates')
    except Exception:
        return {'status':'INCONCLUSIVE','reason':'Initial position unavailable'}
    left,top,right,bottom=bounds
    target=(x+dx,y+dy)
    if not (left <= x < right and top <= y < bottom and left <= target[0] < right and top <= target[1] < bottom):
        return {'status':'INCONCLUSIVE','reason':'Start or target outside verified monitor'}
    started=time.monotonic()
    try:
        result=await bridge.dispatch('mouse_move',{'x':target[0],'y':target[1]})
    except Exception as exc:
        return {'status':'INCONCLUSIVE','reason':f'Dispatch failed: {type(exc).__name__}; completion not confirmed', 'start':(x,y),'target':target}
    if result.status!='completed' or result.result is not True:
        return {'status':'FAIL','reason':'Actuator did not confirm execution','start':(x,y),'target':target}
    try:
        final=read_position()
    except Exception:
        return {'status':'INCONCLUSIVE','reason':'Final position unavailable','start':(x,y),'target':target}
    return {'status':'PASS' if final==target else 'FAIL','start':(x,y),'target':target,'observed':final,
            'elapsed_ms':round((time.monotonic()-started)*1000,2),'speed_verified':False}


def open_lab_window():
    """Explicit WinForms lab: named native controls and in-memory receipts."""
    import clr
    clr.AddReference('System.Windows.Forms')
    clr.AddReference('System.Drawing')
    from System.Drawing import Point, Size
    from System.Windows.Forms import Application, Button, Form, Label, ListBox, TextBox, Panel, BorderStyle
    def configure(control, **properties):
        for name, value in properties.items():
            setattr(control, name, value)
        return control
    form = configure(Form(), Text='BRAINNET — Laboratório seguro', Name='brainnet_capability_lab', ClientSize=Size(390, 450))
    status = configure(Label(), Text='Nenhum botão acionado', Name='lab_status', AccessibleName='Estado do laboratório',
                       Location=Point(20, 135), AutoSize=True)
    log = configure(ListBox(), Name='lab_receipts', AccessibleName='Registro de eventos', Location=Point(20, 165), Size=Size(350, 100))
    entry = configure(TextBox(), Name='lab_text', AccessibleName='Campo de teste', Location=Point(20, 95), Size=Size(350, 24))
    button_a = configure(Button(), Text='TESTE A', Name='lab_button_a', AccessibleName='TESTE A', Location=Point(20, 20), Size=Size(150, 45))
    button_b = configure(Button(), Text='TESTE B', Name='lab_button_b', AccessibleName='TESTE B', Location=Point(200, 20), Size=Size(150, 45))
    motor_label = configure(Label(), Text='ÁREA DE TESTE MOTOR — SEM CLIQUES', Name='lab_motor_label',
                            Location=Point(20, 275), AutoSize=True)
    motor_area = configure(Panel(), Name='lab_motor_area', AccessibleName='Área de teste motor — sem cliques',
                           Location=Point(20, 305), Size=Size(350, 120), BorderStyle=BorderStyle.FixedSingle)
    def record(label):
        status.Text = f'Acionado: {label}'
        log.Items.Add(f'{time.time():.3f} {label}')
    def click_a(sender, event): record('TESTE A')
    def click_b(sender, event): record('TESTE B')
    button_a.Click += click_a
    button_b.Click += click_b
    for control in (button_a, button_b, entry, status, log, motor_label, motor_area):
        form.Controls.Add(control)
    lifecycle_path = os.environ.get('BRAINNET_LAB_LIFECYCLE_LOG')
    if lifecycle_path:
        import datetime
        from System.Windows.Forms import Timer
        def lifecycle(event, detail=''):
            with open(lifecycle_path, 'a', encoding='utf-8') as stream:
                stream.write(f'{datetime.datetime.now().astimezone().isoformat()} {event} {detail}\n')
        def on_load(sender, event): lifecycle('LOAD')
        def on_shown(sender, event): lifecycle('SHOWN', f'hwnd={sender.Handle}')
        def on_closing(sender, event): lifecycle('FORM_CLOSING', f'reason={event.CloseReason} cancel={event.Cancel}')
        def on_closed(sender, event): lifecycle('FORM_CLOSED', f'reason={event.CloseReason}')
        def on_tick(sender, event): lifecycle('MESSAGE_LOOP_TICK')
        form.Load += on_load
        form.Shown += on_shown
        form.FormClosing += on_closing
        form.FormClosed += on_closed
        timer = Timer()
        timer.Interval = 1000
        timer.Tick += on_tick
        timer.Start()
        lifecycle('APPLICATION_RUN_BEGIN', f'pid={os.getpid()}')
    Application.Run(form)
    if lifecycle_path:
        lifecycle('APPLICATION_RUN_RETURNED')


if __name__ == '__main__':
    open_lab_window()


def propose_delegated_move(start, monitor_rect, safe_rect, *, coordinates_verified=False):
    """Pure proposal only; no cursor read, authorization or motor dispatch."""
    if coordinates_verified is not True:
        return {'status': 'ACTION_BLOCKED', 'reason': 'COORDINATE_MISMATCH', 'execution_authorized': False}
    if (not isinstance(start, (tuple, list)) or len(start) != 2 or
        not all(isinstance(r, (tuple, list)) and len(r) == 4 for r in (monitor_rect, safe_rect)) or
        any(type(v) is not int for v in (*start, *monitor_rect, *safe_rect))):
        return {'status': 'ACTION_BLOCKED', 'reason': 'Geometria inválida', 'execution_authorized': False}
    def inside(p, rect):
        return rect[0] <= p[0] < rect[2] and rect[1] <= p[1] < rect[3]
    if not all(inside(start, rect) for rect in (monitor_rect, safe_rect)):
        return {'status': 'ACTION_BLOCKED', 'reason': 'Cursor fora da região segura', 'execution_authorized': False}
    for distance in range(20, 0, -1):
        for dx, dy in ((distance, 0), (-distance, 0), (0, distance), (0, -distance)):
            target = (start[0] + dx, start[1] + dy)
            if all(inside(target, rect) for rect in (monitor_rect, safe_rect)):
                return {'status': 'PROPOSED', 'start': tuple(start), 'target': target,
                        'dx': dx, 'dy': dy, 'execution_authorized': False}
    return {'status': 'ACTION_BLOCKED', 'reason': 'Nenhum deslocamento cabe na região segura', 'execution_authorized': False}


def prepare_delegated_observation(task_id, observation, safe_rect, *, deadline_monotonic, clock=None):
    """Build immutable evidence-bound proposal, without authorizing or dispatching."""
    import time
    import math
    from types import MappingProxyType
    now = (clock or time.monotonic)()
    if not isinstance(task_id, str) or not task_id or type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic) or deadline_monotonic <= now:
        return {'status': 'ACTION_BLOCKED', 'reason': 'Tarefa ou prazo inválido'}
    monitor = observation.get('cursor_monitor') if isinstance(observation, dict) else None
    if not isinstance(monitor, dict) or observation.get('cursor_status') != 'OK' or observation.get('monitor_status') != 'OK' or observation.get('interactive_desktop_verified') is not True:
        return {'status': 'OBSERVATION_UNAVAILABLE', 'reason': 'Cursor, monitor ou desktop indisponível'}
    if not isinstance(monitor.get('device'), str) or not monitor['device']:
        return {'status': 'OBSERVATION_UNAVAILABLE', 'reason': 'Identidade do monitor indisponível'}
    if observation.get('coordinates_compatible') is not True:
        return {'status': 'COORDINATE_MISMATCH', 'reason': 'DPI ou coordenadas não confirmados'}
    proposal = propose_delegated_move(observation.get('cursor'), monitor.get('monitor_rect'), safe_rect, coordinates_verified=True)
    if proposal['status'] != 'PROPOSED':
        return proposal
    return MappingProxyType({'status': 'PROPOSED', 'task_id': task_id, 'action': 'MOVE_CURSOR',
        'start': proposal['start'], 'target': proposal['target'], 'monitor': monitor.get('device'),
        'monitor_rect': tuple(monitor['monitor_rect']), 'safe_rect': tuple(safe_rect),
        'tolerance': 0, 'deadline_monotonic': deadline_monotonic, 'execution_authorized': False})


def observe_physical_cursor(user32=None):
    """Read physical cursor coordinates only; never authorizes or moves input."""
    if user32 is None:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
    position = wintypes.POINT()
    try:
        if not user32.GetPhysicalCursorPos(ctypes.byref(position)):
            return {'status': 'OBSERVATION_UNAVAILABLE', 'source': 'GetPhysicalCursorPos', 'error_code': ctypes.get_last_error()}
        return {'status': 'OBSERVED', 'source': 'GetPhysicalCursorPos', 'cursor': (position.x, position.y), 'timestamp': time.time()}
    except (AttributeError, OSError) as exc:
        return {'status': 'OBSERVATION_UNAVAILABLE', 'source': 'GetPhysicalCursorPos', 'error_type': type(exc).__name__}


def observe_physical_monitor(api=None, cursor_reader=None):
    """Read physical display mode and cursor; no input or approval."""
    if api is None:
        import win32api as api
    if cursor_reader is None:
        cursor_reader = observe_physical_cursor
    cursor = cursor_reader()
    if cursor.get('status') != 'OBSERVED':
        return {'status':'OBSERVATION_UNAVAILABLE', 'reason':'Cursor físico indisponível'}
    try:
        displays = []
        for handle, _, _ in api.EnumDisplayMonitors():
            info = api.GetMonitorInfo(handle)
            mode = api.EnumDisplaySettingsEx(info['Device'], -1, 0)
            x, y = int(mode.Position_x), int(mode.Position_y)
            rect = (x, y, x + int(mode.PelsWidth), y + int(mode.PelsHeight))
            if mode.PelsWidth <= 0 or mode.PelsHeight <= 0:
                raise ValueError('Invalid display mode')
            displays.append((info['Device'], rect))
        point = cursor['cursor']
        matches = [(name, rect) for name, rect in displays if rect[0] <= point[0] < rect[2] and rect[1] <= point[1] < rect[3]]
        if len(matches) != 1:
            return {'status':'OBSERVATION_UNAVAILABLE', 'reason':'Monitor físico não identificado unicamente'}
        name, rect = matches[0]
        return {'status':'OBSERVED', 'cursor':point, 'monitor':name, 'monitor_rect':rect, 'coordinate_space':'PHYSICAL', 'source':'GetPhysicalCursorPos/EnumDisplaySettingsExW', 'timestamp':cursor['timestamp']}
    except Exception as exc:
        return {'status':'OBSERVATION_UNAVAILABLE', 'reason':'Geometria indisponível', 'error_type':type(exc).__name__}


def observe_verified_safe_region(lab_hwnd, lab_pid, safe_rect):
    """No region is trusted until live identity and complete controls are verified."""
    return {'status': 'SAFE_REGION_UNVERIFIED',
            'reason': 'Nenhum provedor existente comprova atualmente a região física e a ausência de controles após o clique.'}


def find_verified_safe_region(observation):
    """Fail closed until a live physical region/control verifier is connected."""
    return {'status':'SAFE_REGION_UNVERIFIED', 'reason':'Região livre de controles não foi comprovada por observação atual.'}
