"""Paint capabilities and factual result contract; no motor or model I/O."""
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass(frozen=True)
class AppContext:
    app: str
    process_name: str
    pid: int
    hwnd: int
    process_started: float
    validated_at: float
    known_capabilities: tuple[str, ...] = ()
    observed_controls: tuple[dict, ...] = ()
    semantic_operations: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    expected_effects: tuple[str, ...] = ()
    available_strategies: tuple[str, ...] = ()

@dataclass
class ExecutionEvidence:
    intent: str
    app: str
    semantic_targets: list[str] = field(default_factory=list)
    strategy: Optional[str] = None
    executed_actions: list[dict[str, Any]] = field(default_factory=list)
    verified_effects: list[dict[str, Any]] = field(default_factory=list)
    goal_state: str = 'GOAL_UNVERIFIED'
    def as_learning_candidate(self):
        # Merely emitting this contract never writes to P-DAG or marks it verified.
        return {'intent':self.intent,'app':self.app,'semantic_targets':list(self.semantic_targets),
                'strategy':self.strategy,'executed_actions':list(self.executed_actions),
                'verified_effects':list(self.verified_effects),'goal_state':self.goal_state,
                'eligible_for_consolidation':bool(self.goal_state=='GOAL_VERIFIED' and self.executed_actions and self.verified_effects)}

def paint_context(task_context, observed_controls=()):
    """Describe capabilities; a declared operation is not evidence it is executable."""
    if task_context is None or task_context.process_name.casefold() not in ('mspaint.exe','mspaint'):
        return None
    return AppContext(app='paint',process_name=task_context.process_name,pid=task_context.pid,
        hwnd=task_context.hwnd,process_started=task_context.process_started,validated_at=task_context.validated_at,
        known_capabilities=('UIA_DISCOVERY','VISUAL_FALLBACK_REQUIRES_AUTHORIZATION'),
        observed_controls=tuple(observed_controls),semantic_operations=('OPEN_BRUSHES_MENU','DRAW_CIRCLE'),
        preconditions=('CURRENT_WINDOW_AND_PROCESS','SERIALIZED_REVALIDATION','USER_CONTROL_CLEAR','AUTHORIZATION'),
        expected_effects=('BRUSHES_MENU_EXPANDED','RED_CIRCLE_VERIFIED'),
        available_strategies=('UIA','AUTHORIZED_VISUAL_FALLBACK'))

def plan_draw_circle(context, *, color='red', verified_canvas_rect=None):
    if context is None or context.app!='paint':return {'status':'CONTEXT_UNAVAILABLE','steps':[]}
    if color.casefold() not in ('red','vermelho'):return {'status':'UNSUPPORTED_COLOR','steps':[]}
    steps=[{'operation':'SELECT_ELLIPSE','requires':'VERIFIED_UIA_TARGET'},
           {'operation':'SELECT_COLOR','target':'red','requires':'VERIFIED_UIA_TARGET'},
           {'operation':'IDENTIFY_CANVAS','requires':'VERIFIED_CANVAS_RECT'},
           {'operation':'DRAW_CIRCLE','requires':'AUTHORIZED_DRAG'},
           {'operation':'VERIFY_GOAL','requires':'VISUAL_GEOMETRIC_AND_COLOR_EVIDENCE'}]
    # A rectangle alone is not proof of its source or that it is a canvas.
    return {'status':'GOAL_UNVERIFIED','steps':steps,'verified_canvas_rect':None,
            'reason':'Canvas, controls, authorization and factual goal must be independently verified.'}

def visual_fallback_advice(*, uia_status, explicit_authorization, resource_approved):
    if uia_status not in ('TARGET_NOT_FOUND','UIA_UNAVAILABLE'):
        return {'decision':'DENIED','reason':'UIA result does not permit fallback'}
    if explicit_authorization is not True or resource_approved is not True:
        return {'decision':'DENIED','reason':'explicit authorization and resource approval required'}
    return {'decision':'ELIGIBLE','reason':'caller must invoke existing visual protocol explicitly'}
