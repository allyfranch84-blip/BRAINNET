"""Live UIA grounding for a user-selected window. No stored coordinates or COM objects."""
import math
import os
import time
import uuid
import unicodedata

CONTROL_TYPES = frozenset(('ButtonControl','SplitButtonControl','MenuItemControl','TabItemControl',
    'CheckBoxControl','RadioButtonControl','ComboBoxControl','EditControl','ListItemControl',
    'TreeItemControl','HyperlinkControl','SliderControl','ScrollBarControl','DataItemControl',
    'MenuBarControl','ToolBarControl'))


def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold())
                           if not unicodedata.combining(c)).split())


def find_window(query):
    import win32gui, win32process
    import psutil
    from uia_chat_readonly import inspect_window
    key = normalize(query)
    if not key:
        return {'status':'TARGET_REQUIRED'}
    matches = []
    def visit(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == os.getpid():
                return True
            title = win32gui.GetWindowText(hwnd)
            process = psutil.Process(pid).name()
            if not title or not (key in normalize(title) or key in normalize(process)):
                return True
            identity = inspect_window(hwnd)
            if identity and identity['pid'] == pid:
                matches.append({**identity,'app':process})
        except Exception:
            pass
        return True
    win32gui.EnumWindows(visit, None)
    if len(matches) != 1:
        return {'status':'TARGET_AMBIGUOUS' if matches else 'TARGET_NOT_FOUND','count':len(matches)}
    return {'status':'BOUND','window':matches[0]}


def same_window(window, *, foreground=False):
    import win32gui
    from uia_chat_readonly import inspect_window
    try:
        current = inspect_window(window['hwnd'])
        return bool(current and current['pid']==window['pid'] and current['started']==window['started']
                    and not win32gui.IsIconic(window['hwnd'])
                    and (not foreground or win32gui.GetForegroundWindow()==window['hwnd']))
    except Exception:
        return False


def eligible_controls(rows, pid):
    result = []
    for row in rows:
        name = row.get('name')
        rect = row.get('rect')
        runtime = row.get('runtime_id')
        if (row.get('process_id') != pid or (row.get('control_type') not in CONTROL_TYPES
                and row.get('invoke_supported') is not True and row.get('expand_collapse_supported') is not True)
            or not isinstance(name,str) or not name.strip() or len(name)>160
            or row.get('is_enabled') is not True or row.get('is_offscreen') is not False
            or not isinstance(runtime,(list,tuple)) or not runtime
            or not isinstance(rect,(list,tuple)) or len(rect)!=4
            or any(type(v) is not int for v in rect) or rect[0]>=rect[2] or rect[1]>=rect[3]):
            continue
        result.append({'name':name,'type':row['control_type'],'runtime_id':tuple(runtime),
                       'rect':tuple(rect),'automation_id':row.get('automation_id')})
    return result


def observe(window, eye, *, foreground=False):
    if not same_window(window,foreground=foreground):
        return {'status':'CONTEXT_CHANGED','controls':[]}
    try:
        rows = eye.scan_uia_properties(window['hwnd'],max_controls=1200,max_depth=24)
        if not same_window(window,foreground=foreground):
            return {'status':'CONTEXT_CHANGED','controls':[]}
        controls = eligible_controls(rows,window['pid'])
        # A bounded scan cannot establish uniqueness if it reached its limit.
        if len(rows)>=1200:
            return {'status':'SCAN_LIMIT','controls':[]}
        return {'status':'OBSERVED' if controls else 'NO_VISIBLE_CONTROLS','controls':controls,'raw_count':len(rows)}
    except Exception:
        return {'status':'UIA_UNAVAILABLE','controls':[]}


def resolve_target(controls, name):
    key = normalize(name)
    matches = [c for c in controls if normalize(c['name']) == key]
    if not matches:
        matches = [c for c in controls if c.get('automation_id') and normalize(c['automation_id']) == key]
    if len(matches)!=1:
        return {'status':'TARGET_AMBIGUOUS' if matches else 'TARGET_NOT_FOUND','count':len(matches)}
    return {'status':'RESOLVED','control':matches[0]}


def center(rect):
    return ((rect[0]+rect[2]-1)//2,(rect[1]+rect[3]-1)//2)


def waypoints(start,target,limit=150):
    distance=math.dist(start,target)
    count=math.ceil(distance/(limit-2))
    if count>32:
        raise ValueError('TARGET_TOO_FAR')
    return list(dict.fromkeys((round(start[0]+(target[0]-start[0])*i/count),
                               round(start[1]+(target[1]-start[1])*i/count))
                              for i in range(1,count+1))) if count else []


def hit_target(point, window, descriptor):
    """UIA point coordinates are physical screen coordinates; verify the actual hit or its ancestor."""
    import uiautomation as auto
    if not same_window(window,foreground=True):
        return False
    try:
        with auto.UIAutomationInitializerInThread():
            control=auto.ControlFromPoint(*point)
            for _ in range(12):
                if control is None:
                    break
                if (int(control.ProcessId)==window['pid'] and tuple(control.GetRuntimeId())==descriptor['runtime_id']):
                    r=control.BoundingRectangle
                    return (control.IsEnabled is True and control.IsOffscreen is False
                            and (int(r.left),int(r.top),int(r.right),int(r.bottom))==descriptor['rect'])
                control=control.GetParentControl()
    except Exception:
        pass
    return False


def execute_target(window, step, eye, effector, *, task_id, deadline, expected_cursor, expected_foreground):
    """One serialized motor operation; select/reobserve/hit-test target before using existing motor."""
    from execution_authority import require_action_allowed, PhysicalMoveProposal, PhysicalMoveApproval, approved_physical_move_scope
    from capability_lab import observe_physical_monitor, observe_cursor_monitors
    from motor_intent import validate_plan
    import win32gui, win32process
    from effector import user32

    evidence=[]
    def result(code,status='ACTION_BLOCKED',**extra):
        return {'status':status,'code':code,'dispatched':bool(evidence),'waypoints':list(evidence),**extra}
    def active():
        require_action_allowed('UI_TARGET')
        if time.monotonic()>=deadline:
            raise TimeoutError('UI_TARGET_EXPIRED')
    def unchanged(obs,expected):
        return (obs.get('status')=='OBSERVED' and obs.get('coordinate_space')=='PHYSICAL'
                and all(obs.get(k)==expected.get(k) for k in ('cursor','monitor','monitor_rect')))
    def held():
        return any(user32.GetAsyncKeyState(vk)&0x8000 for vk in (1,2,4,5,6))

    validate_plan({'status':'execute','steps':[step]})
    if step['action'] not in ('move_to','click_target'):
        return result('INVALID_TARGET_ACTION')
    active()
    if not same_window(window) or observe_cursor_monitors().get('interactive_desktop_verified') is not True:
        return result('CONTEXT_UNAVAILABLE')
    before=observe_physical_monitor()
    if not unchanged(before,expected_cursor) or held():
        return result('USER_INPUT_CHANGED')
    foreground=win32gui.GetForegroundWindow()
    # A transition to the exact selected window is useful, not a conflicting target.
    if foreground!=expected_foreground and foreground!=window['hwnd']:
        return result('FOCUS_CHANGED',expected_focus=expected_foreground,observed_focus=foreground,target_hwnd=window['hwnd'])
    if foreground!=window['hwnd']:
        try:
            _,pid=win32process.GetWindowThreadProcessId(foreground)
            if pid!=os.getpid():
                return result('FOCUS_NOT_OWNED',expected_focus=expected_foreground,observed_focus=foreground,target_hwnd=window['hwnd'])
            active()
            win32gui.SetForegroundWindow(window['hwnd'])
        except Exception:
            return result('FOCUS_UNAVAILABLE')
    if not same_window(window,foreground=True):
        return result('FOCUS_UNAVAILABLE',observed_focus=win32gui.GetForegroundWindow(),target_hwnd=window['hwnd'])
    scene=observe(window,eye,foreground=True)
    if scene['status']!='OBSERVED':
        return result(scene['status'])
    match=resolve_target(scene['controls'],step['target'])
    if match['status']!='RESOLVED':
        return result(match['status'],control_count=len(scene['controls']),raw_count=scene.get('raw_count'))
    descriptor=match['control']
    target=center(descriptor['rect'])
    rect=tuple(before['monitor_rect'])
    if not (rect[0]<=target[0]<rect[2] and rect[1]<=target[1]<rect[3]):
        return result('TARGET_OTHER_MONITOR',target=target)
    if not hit_target(target,window,descriptor):
        return result('TARGET_OCCLUDED_OR_STALE')
    if not unchanged(observe_physical_monitor(),before):
        return result('USER_INPUT_CHANGED')
    start=tuple(before['cursor'])
    try:
        points=waypoints(start,target)
    except ValueError:
        return result('TARGET_TOO_FAR')
    for point in points:
        active()
        current=observe_physical_monitor()
        if (not same_window(window,foreground=True)
                or not unchanged(current,{**before,'cursor':start}) or held()):
            return result('CONTEXT_CHANGED','PARTIAL' if evidence else 'ACTION_BLOCKED')
        proposal=PhysicalMoveProposal(task_id,uuid.uuid4().hex,start,point,before['monitor'],rect,0,deadline,
                                      max_distance=150,duration_ms=300)
        approval=PhysicalMoveApproval(proposal)
        if not approval.approve_explicitly(proposal.proposal_id) or not approval.consume(proposal,current):
            return result('SEGMENT_REJECTED','PARTIAL' if evidence else 'ACTION_BLOCKED')
        try:
            with approved_physical_move_scope(proposal):
                ok=effector.mouse_move(*point,profile='physical_diagnostic',tolerance=0)
        except Exception:
            return result('MOVE_INTERRUPTED','EFFECT_UNVERIFIED',dispatched=True)
        actual=observe_physical_monitor()
        if ok is not True or not unchanged(actual,{**before,'cursor':point}):
            return result('MOVE_NOT_CONFIRMED','EFFECT_UNVERIFIED',after=actual.get('cursor'),dispatched=True)
        evidence.append(point)
        start=point
    active()
    if (not hit_target(target,window,descriptor)
            or not unchanged(observe_physical_monitor(),{**before,'cursor':target}) or held()):
        return result('TARGET_CHANGED','PARTIAL' if evidence else 'ACTION_BLOCKED')
    if step['action']=='move_to':
        return result('TARGET_HIT_VERIFIED','EFFECT_VERIFIED',target=target,name=descriptor['name'],
                      control_type=descriptor['type'],dispatched=bool(evidence))
    active()
    ok=effector.mouse_click(step['button'],step['count'])
    return result('INPUT_ACCEPTED' if ok is True else 'INPUT_NOT_CONFIRMED',
                  'INPUT_SENT' if ok is True else 'EFFECT_UNVERIFIED',
                  target=target,name=descriptor['name'],control_type=descriptor['type'],
                  sent_count=step['count'] if ok is True else None,dispatched=True)
