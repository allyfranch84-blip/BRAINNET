"""Revalidated UI Automation actions; no COM objects cross threads."""
import ctypes
from ctypes import wintypes
import psutil
from execution_authority import current_authorization, require_action_allowed


def last_input_snapshot():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_=[('cbSize',wintypes.UINT),('dwTime',wintypes.DWORD)]
    info=LASTINPUTINFO();info.cbSize=ctypes.sizeof(info)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):return None
        now=ctypes.windll.kernel32.GetTickCount() & 0xffffffff
        return {'tick':int(info.dwTime),'idle_ms':(now-int(info.dwTime))&0xffffffff}
    except (OSError,AttributeError):return None


def activate_ui_control(descriptor, action, *, value=None, baseline_input=None):
    """Called inside the actuator lock, in one dedicated COM-initialized thread."""
    require_action_allowed('ACTIVATE_UI_CONTROL')
    token=current_authorization()
    if token is None or token.is_set():return {'status':'ACTION_BLOCKED','reason':'authorization unavailable or revoked'}
    if action not in ('CLICK','EXPAND','SELECT','TOGGLE','SET_VALUE'):
        return {'status':'ACTION_BLOCKED','reason':'unsupported intent'}
    if not isinstance(descriptor,dict) or not descriptor.get('name') or not descriptor.get('runtime_id'):
        return {'status':'ACTION_BLOCKED','reason':'target identity incomplete'}
    sent=False
    try:
        hwnd=int(descriptor['hwnd']);pid=int(descriptor['pid']);birth=float(descriptor['process_started'])
        if ctypes.windll.user32.GetForegroundWindow()!=hwnd or not ctypes.windll.user32.IsWindow(hwnd):
            return {'status':'ACTION_BLOCKED','reason':'window not foreground or expired'}
        current_pid=wintypes.DWORD();ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(current_pid))
        if current_pid.value!=pid or psutil.Process(pid).create_time()!=birth:
            return {'status':'ACTION_BLOCKED','reason':'process identity changed'}
        current=last_input_snapshot()
        if (not isinstance(baseline_input,dict) or not isinstance(current,dict) or
            current.get('tick')!=baseline_input.get('tick') or current.get('idle_ms',0)<750):
            return {'status':'ACTION_BLOCKED','reason':'recent or unknown user activity'}
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            root=auto.ControlFromHandle(hwnd)
            if not root.Exists(0,0):return {'status':'ACTION_BLOCKED','reason':'window UIA unavailable'}
            matches=[]
            for control,depth in auto.WalkTree(root,getChildren=lambda c:c.GetChildren()):
                if depth>6:continue
                try:
                    if str(control.Name).casefold()!=str(descriptor['name']).casefold():continue
                    if int(control.ProcessId)!=pid:continue
                    matches.append(control)
                except Exception:continue
            if len(matches)!=1:return {'status':'ACTION_BLOCKED','reason':'target stale or ambiguous'}
            control=matches[0]
            if (tuple(control.GetRuntimeId())!=tuple(descriptor['runtime_id']) or
                (descriptor.get('automation_id') and control.AutomationId!=descriptor['automation_id']) or
                (descriptor.get('control_type') and control.ControlTypeName!=descriptor['control_type'])):
                return {'status':'ACTION_BLOCKED','reason':'target identity changed'}
            if control.IsEnabled is not True or control.IsOffscreen is not False:
                return {'status':'ACTION_BLOCKED','reason':'target disabled, offscreen or unknown'}
            # Recheck after UIA traversal, inside the same serialised operation.
            require_action_allowed('ACTIVATE_UI_CONTROL')
            latest=last_input_snapshot()
            if token.is_set() or ctypes.windll.user32.GetForegroundWindow()!=hwnd or not latest or latest.get('tick')!=baseline_input.get('tick'):
                return {'status':'ACTION_BLOCKED','reason':'authority, focus or user input changed'}
            def get_pattern(name):
                try:
                    p=getattr(control,name)()
                    return p if p is not None and getattr(p,'pattern',None) is not None else None
                except Exception:return None
            pattern=None;method=None;before=None
            if action in ('CLICK','EXPAND'):
                pattern=get_pattern('GetExpandCollapsePattern')
                if pattern is not None:
                    before=pattern.ExpandCollapseState;method='EXPAND'
                elif action=='CLICK':pattern=get_pattern('GetInvokePattern');method='INVOKE'
            elif action=='SELECT':pattern=get_pattern('GetSelectionItemPattern');method='SELECT';before=pattern.IsSelected if pattern else None
            elif action=='TOGGLE':pattern=get_pattern('GetTogglePattern');method='TOGGLE';before=pattern.ToggleState if pattern else None
            elif action=='SET_VALUE':
                if not isinstance(value,str):return {'status':'ACTION_BLOCKED','reason':'string value required'}
                pattern=get_pattern('GetValuePattern');method='SET_VALUE';before=pattern.Value if pattern else None
            if pattern is None:return {'status':'ACTION_BLOCKED','reason':'compatible UIA pattern unavailable; visual fallback requires approval'}
            require_action_allowed('ACTIVATE_UI_CONTROL')
            sent=True
            if method=='EXPAND':ok=pattern.Expand(waitTime=0)
            elif method=='INVOKE':ok=pattern.Invoke(waitTime=0)
            elif method=='SELECT':ok=pattern.Select(waitTime=0)
            elif method=='TOGGLE':ok=pattern.Toggle(waitTime=0)
            else:ok=pattern.SetValue(value,waitTime=0)
            if ok is not True:return {'status':'ACTION_FAILED','reason':'UIA operation failed','method':method}
            effect=False
            try:
                if method=='EXPAND':effect=before != pattern.ExpandCollapseState and pattern.ExpandCollapseState==1
                elif method=='SELECT':effect=pattern.IsSelected is True
                elif method=='TOGGLE':effect=before != pattern.ToggleState
                elif method=='SET_VALUE':effect=pattern.Value==value
            except Exception:pass
            return {'status':'EFFECT_VERIFIED' if effect else 'GOAL_UNVERIFIED',
                    'action_state':'ACTION_EXECUTED','effect_verified':effect,'goal_verified':False,
                    'method':method,'reason':'UIA effect observed' if effect else 'effect not independently verified'}
    except Exception as exc:
        return {'status':'ACTION_FAILED' if sent else 'ACTION_BLOCKED','reason':f'UIA operation failed: {type(exc).__name__}'}
