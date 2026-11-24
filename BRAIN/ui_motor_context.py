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


def same_window(window, *, foreground=False, allow_minimized=False):
    import win32gui
    from uia_chat_readonly import inspect_window
    try:
        current = inspect_window(window['hwnd'])
        return bool(current and current['pid']==window['pid'] and current['started']==window['started']
                    and (allow_minimized or not win32gui.IsIconic(window['hwnd']))
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


def stable_foreground(*, deadline):
    """Zero is an incomplete observation during a Windows focus transition."""
    import win32gui
    hwnd=win32gui.GetForegroundWindow()
    end=min(deadline,time.monotonic()+.8)
    while not hwnd and time.monotonic()<end:
        time.sleep(.025)
        hwnd=win32gui.GetForegroundWindow()
    return int(hwnd or 0)


def activate_selected_window(window, expected_foreground, *, deadline, previous_window=None):
    """Transfer focus only from our own chat to the explicitly selected window."""
    from execution_authority import require_action_allowed
    import win32gui, win32process
    def result(code, current):
        return {'status':'READY' if code=='FOCUS_READY' else 'ACTION_BLOCKED',
                'code':code,'expected_focus':expected_foreground,
                'observed_focus':current,'target_hwnd':window['hwnd']}
    require_action_allowed('UI_TARGET')
    current=stable_foreground(deadline=deadline)
    if not same_window(window,allow_minimized=True):
        return result('CONTEXT_UNAVAILABLE',current)
    if current==window['hwnd'] and same_window(window,foreground=True):
        return result('FOCUS_READY',current)
    if not current:
        return result('FOCUS_TRANSITION_TIMEOUT',0)
    if expected_foreground and current!=expected_foreground:
        return result('FOCUS_CHANGED',current)
    try:
        _,pid=win32process.GetWindowThreadProcessId(current)
        previous_verified=(previous_window is not None and current==previous_window['hwnd'] and same_window(previous_window,foreground=True))
        if pid!=os.getpid() and not previous_verified and current!=window['hwnd']:
            return result('FOCUS_NOT_OWNED',current)
        require_action_allowed('UI_TARGET')
        if time.monotonic()>=deadline:
            return result('FOCUS_EXPIRED',current)
        try:
            if win32gui.GetWindowPlacement(window['hwnd'])[1] in (2,6,7):
                win32gui.ShowWindow(window['hwnd'],9)
            require_action_allowed('UI_TARGET')
            win32gui.SetForegroundWindow(window['hwnd'])
        except Exception:
            # The API can report failure even while the activation is in flight.
            pass
    except Exception:
        return result('FOCUS_UNAVAILABLE',win32gui.GetForegroundWindow())
    end=min(deadline,time.monotonic()+1.2)
    while time.monotonic()<end:
        require_action_allowed('UI_TARGET')
        observed=win32gui.GetForegroundWindow()
        if observed==window['hwnd'] and same_window(window,foreground=True):
            return result('FOCUS_READY',observed)
        if observed and observed!=current:
            return result('FOCUS_CHANGED',observed)
        time.sleep(.04)
    return result('FOCUS_UNAVAILABLE',win32gui.GetForegroundWindow())


def observe_active(window, eye, *, expected_foreground, deadline):
    focus=activate_selected_window(window,expected_foreground,deadline=deadline)
    if focus['status']!='READY':
        # A read-only inspection can still describe an inactive window.
        scene=observe(window,eye,foreground=False)
        return {**scene,'foreground_verified':False,'focus_code':focus['code']}
    return {**observe(window,eye,foreground=True),'foreground_verified':True}


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
        from collections import Counter
        eligible_ids={c['runtime_id'] for c in controls}
        rejected=[]
        reasons=Counter()
        for row in rows:
            runtime=row.get('runtime_id')
            if isinstance(runtime,(tuple,list)) and tuple(runtime) in eligible_ids:
                continue
            if row.get('process_id')!=window['pid']:
                reasons['outro processo']+=1
                continue
            name=row.get('name')
            if not isinstance(name,str) or not name.strip():
                reasons['sem nome']+=1
                continue
            if row.get('is_offscreen') is True:
                reason='fora da vista'
            elif row.get('is_enabled') is not True:
                reason='desabilitado/estado desconhecido'
            elif row.get('control_type') not in CONTROL_TYPES and row.get('invoke_supported') is not True and row.get('expand_collapse_supported') is not True:
                reason='tipo sem interação reconhecida'
            else:
                reason='identidade/geometria/visibilidade incompleta'
            reasons[reason]+=1
            # Only control labels, never read edit/document values.
            if row.get('control_type') not in ('EditControl','DocumentControl','TextControl') and len(name)<=160:
                rejected.append({'name':name,'type':row.get('control_type'),'reason':reason})
        return {'status':'OBSERVED' if controls else 'NO_VISIBLE_CONTROLS','controls':controls,'raw_count':len(rows),
                'rejection_counts':dict(reasons),'rejected':rejected[:150]}
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
    if descriptor.get('source')=='OCR':
        from ui_ocr_grounding import revalidate
        return revalidate(point,window,descriptor)
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
    focus=activate_selected_window(window,expected_foreground,deadline=deadline)
    if focus['status']!='READY':
        return result(focus['code'],expected_focus=focus.get('expected_focus'),
                      observed_focus=focus.get('observed_focus'),target_hwnd=window['hwnd'])
    # Focus first, then anchor the motor to the current physical cursor.
    # A changed cursor during the focus handoff is not silently accepted.
    if not unchanged(observe_physical_monitor(),before) or held():
        return result('USER_INPUT_CHANGED')
    scene=observe(window,eye,foreground=True)
    match=resolve_target(scene.get('controls',[]),step['target'])
    if scene['status'] not in ('OBSERVED','NO_VISIBLE_CONTROLS','UIA_UNAVAILABLE'):
        return result(scene['status'])
    if match['status']=='TARGET_NOT_FOUND':
        from ui_ocr_grounding import find_text
        active()
        visual=find_text(window,step['target'])
        active()
        if visual['status']=='RESOLVED':
            if step['action']=='click_target':
                return result('OCR_AFFORDANCE_UNVERIFIED',status='OBSERVED',name=visual['control']['name'],
                              target=center(visual['control']['rect']),source='OCR')
            match=visual
        else:
            return result('TARGET_NOT_FOUND',control_count=len(scene.get('controls',[])),raw_count=scene.get('raw_count'),
                          rejected_matches=[c for c in scene.get('rejected',[]) if normalize(step['target']) in normalize(c['name'])][:8],
                          similar_names=[c['name'] for c in scene.get('controls',[]) if normalize(step['target']) in normalize(c['name'])][:8],
                          ocr_status=visual['status'],ocr_error=visual.get('error'),ocr_similar=visual.get('similar',[]))
    if match['status']!='RESOLVED':
        return result(match['status'],control_count=len(scene.get('controls',[])),raw_count=scene.get('raw_count'))
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
                      control_type=descriptor['type'],source=descriptor.get('source','UIA'),dispatched=bool(evidence))
    active()
    ok=effector.mouse_click(step['button'],step['count'])
    return result('INPUT_ACCEPTED' if ok is True else 'INPUT_NOT_CONFIRMED',
                  'INPUT_SENT' if ok is True else 'EFFECT_UNVERIFIED',
                  target=target,name=descriptor['name'],control_type=descriptor['type'],
                  sent_count=step['count'] if ok is True else None,dispatched=True)


def open_application(app, *, deadline):
    """Launch only an enumerated OS application, then verify the live window."""
    from execution_authority import require_action_allowed
    import subprocess
    import win32api
    import win32gui
    mapping = {
        'paint': ('mspaint.exe', ('mspaint.exe',)),
        'notepad': ('notepad.exe', ('notepad.exe',)),
        'calculator': ('calc.exe', ('CalculatorApp.exe','Calculator.exe','calc.exe')),
    }
    if app not in mapping:
        return {'status':'ACTION_BLOCKED','code':'UNKNOWN_APP','dispatched':False}
    executable, processes = mapping[app]
    def lookup():
        import win32process
        import psutil
        from uia_chat_readonly import inspect_window
        windows = []
        def visit(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                    return True
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid).name()
                if process.casefold() in tuple(p.casefold() for p in processes):
                    identity = inspect_window(hwnd)
                    if identity and identity['pid'] == pid:
                        windows.append({**identity,'app':process})
            except Exception:
                pass
            return True
        win32gui.EnumWindows(visit, None)
        return windows
    def check():
        require_action_allowed('OPEN_APP')
        if time.monotonic() >= deadline:
            raise TimeoutError('OPEN_APP_EXPIRED')
    check()
    matches=lookup()
    launched=False
    if not matches:
        path=os.path.join(win32api.GetSystemDirectory(),executable)
        if not os.path.isfile(path):
            return {'status':'UNAVAILABLE','code':'APP_EXECUTABLE_MISSING','dispatched':False}
        check()
        subprocess.Popen([path],shell=False)
        launched=True
        while time.monotonic() < deadline:
            check()
            matches=lookup()
            if matches:
                break
            time.sleep(.15)
    if len(matches)!=1:
        return {'status':'GOAL_UNVERIFIED' if launched else 'ACTION_BLOCKED',
                'code':'APP_WINDOW_AMBIGUOUS' if matches else 'APP_WINDOW_UNCONFIRMED',
                'dispatched':launched}
    window=matches[0]
    check()
    # Do not steal focus from an unrelated application. A verified open window
    # is sufficient to bind context; physical actions revalidate focus separately.
    focused=win32gui.GetForegroundWindow()==window['hwnd']
    return {'status':'EFFECT_VERIFIED','code':'APP_WINDOW_VERIFIED','window':window,
            'focused':focused,'dispatched':launched}
