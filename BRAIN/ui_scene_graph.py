"""Ephemeral application-neutral UI scene graph; perception only, never acts."""
from dataclasses import dataclass, field, asdict
from enum import Enum
import math
import time
import uuid

class Action(str,Enum):
    CLICK='CLICK'; EXPAND='EXPAND'; SELECT='SELECT'; SET_VALUE='SET_VALUE'; TYPE='TYPE'; SCROLL='SCROLL'; DRAG='DRAG'; OPEN='OPEN'; CLOSE='CLOSE'

@dataclass(frozen=True)
class Evidence:
    source: str
    role: str
    name: str
    bbox: tuple | None
    state: dict
    interactions: tuple
    confidence: float | None
    coordinate_space: str
    verified: bool = False
    reference: str | None = None
    relations: tuple = ()
    def __post_init__(self):
        if self.source not in ('UIA','DOM','OCR','VISION'): raise ValueError('unsupported source')
        if self.bbox is not None:
            if len(self.bbox)!=4 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in self.bbox) or not (self.bbox[0]<self.bbox[2] and self.bbox[1]<self.bbox[3]): raise ValueError('invalid bbox')
        if self.confidence is not None and (isinstance(self.confidence,bool) or not isinstance(self.confidence,(int,float)) or not 0<=self.confidence<=1): raise ValueError('invalid confidence')
        if any(x not in Action._value2member_map_ for x in self.interactions):raise ValueError('invalid interaction')
        if self.source in ('VISION','OCR') and self.verified:raise ValueError('visual inference is not verified')

@dataclass
class SceneElement:
    element_id: str
    role: str
    name: str
    bbox: tuple | None
    evidence: list[Evidence]
    relations: list = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    @property
    def possible_interactions(self): return sorted({a for e in self.evidence for a in e.interactions})
    def to_dict(self):
        d=asdict(self);d['possible_interactions']=self.possible_interactions
        # Observation does not authorize execution, even if UIA reported a pattern.
        d['action_authorized']=False;return d

def overlap(a,b):
    if not a or not b:return 0.0
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]));inter=x*y
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter
    return inter/union if union>0 else 0.0

def _role(value):
    v=str(value or 'unknown').casefold().replace('control','').strip()
    return {'edit':'textbox','text':'text','document':'document','tabitem':'tab','menuitem':'menuitem'}.get(v,v or 'unknown')

def uia_evidence(row, *, coordinate_space='screen_physical'):
    role=_role(row.get('control_type')); acts=[]
    if row.get('invoke_supported') is True:acts.append('CLICK')
    if row.get('expand_collapse_supported') is True:acts.append('EXPAND')
    return Evidence('UIA',role,str(row.get('name') or ''),tuple(row['rect']) if row.get('rect') else None,
        {'enabled':row.get('is_enabled'),'offscreen':row.get('is_offscreen')},tuple(acts),None,coordinate_space,
        verified=False,reference=str(row.get('runtime_id')) if row.get('runtime_id') else None)

@dataclass
class UISceneGraph:
    observation_id: str
    app: dict
    observed_at: float
    frame: dict
    elements: list[SceneElement]
    warnings: list[str] = field(default_factory=list)
    def to_dict(self):return {'observation_id':self.observation_id,'app':dict(self.app),'observed_at':self.observed_at,
        'frame':dict(self.frame),'elements':[e.to_dict() for e in self.elements],'warnings':list(self.warnings)}
    def find(self,name):
        key=str(name).strip().casefold()
        return [e for e in self.elements if e.name.strip().casefold()==key]
    def assess_target(self, name):
        """Report observed risk indicators, not a calibrated failure probability."""
        matches = self.find(name)
        reasons = []
        if not matches:
            reasons.append('target_not_observed')
        elif len(matches) != 1:
            reasons.append('target_ambiguous')
        else:
            element = matches[0]
            if not element.bbox:
                reasons.append('bounds_unknown')
            if element.uncertainty:
                reasons.extend(element.uncertainty)
            if not any(e.source in ('UIA', 'DOM') for e in element.evidence):
                reasons.append('no_native_control_evidence')
        return {'target': str(name), 'indicators': sorted(set(reasons)),
                'recommendation': 'REOBSERVE_OR_ALTERNATIVE' if reasons else 'REVALIDATE_BEFORE_ACTION',
                'probability': None, 'action_authorized': False}
    def valid_for(self,*,hwnd,pid,now,process_started=None,observation_id=None,max_age=5):
        # Reuse requires an independently checked observation and process birth time.
        return (process_started is not None and observation_id==self.observation_id and
                self.app.get('process_started')==process_started and self.app.get('hwnd')==hwnd and
                self.app.get('pid')==pid and 0<=now-self.observed_at<=max_age)

def build_scene_graph(*,app,frame,uia=(),dom=(),ocr=(),visual=(),observed_at=None):
    """Fuse only mutually unique overlaps from different sources in the same coordinate space."""
    if not isinstance(app,dict) or not isinstance(frame,dict):raise ValueError('app and frame must be dicts')
    timestamp=time.monotonic() if observed_at is None else observed_at
    if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp):raise ValueError('invalid timestamp')
    obs=uuid.uuid4().hex;records=[]
    for source,items in [('UIA',uia),('DOM',dom),('OCR',ocr),('VISION',visual)]:
        for row in items:
            registered = (frame.get('registration_id') is not None and row.get('registration_id') == frame.get('registration_id'))
            e=uia_evidence(row) if source=='UIA' else Evidence(source,_role(row.get('role')),str(row.get('name') or ''),
                tuple(row['bbox']) if row.get('bbox') else None,dict(row.get('state') or {}),tuple(row.get('interactions') or ()),
                row.get('confidence'),str(row.get('coordinate_space') or 'UNKNOWN') if registered else 'UNKNOWN',verified=False,
                reference=str(row['reference']) if row.get('reference') is not None else None,relations=tuple(row.get('relations') or ()))
            records.append(e)
    # UIA/DOM before probabilistic sources; DOM wins over UIA for equivalent page controls.
    records.sort(key=lambda e:{'DOM':0,'UIA':1,'OCR':2,'VISION':3}[e.source])
    nodes=[]
    for i,e in enumerate(records):
        matches=[]
        for node in nodes:
            if any(a.source==e.source for a in node.evidence):continue
            first=node.evidence[0]
            if e.coordinate_space=='UNKNOWN' or e.coordinate_space!=first.coordinate_space:continue
            if e.role!='unknown' and node.role!='unknown' and e.role!=node.role:continue
            if overlap(node.bbox,e.bbox)>=.8:matches.append(node)
        # Do not merge if another same-source detection could claim that node.
        unambiguous=len(matches)==1 and sum(1 for other in records if other.source==e.source and other.coordinate_space==e.coordinate_space and other.bbox and overlap(matches[0].bbox,other.bbox)>=.8)==1
        if unambiguous:
            node=matches[0];node.evidence.append(e)
            for k,v in e.state.items():
                prior=[z.state[k] for z in node.evidence[:-1] if k in z.state and z.state[k] is not None]
                if v is not None and prior and any(x!=v for x in prior):node.uncertainty.append('conflicting_'+k)
            if not node.name and e.name:node.name=e.name
        else:
            warnings=['visual_or_ocr_hypothesis'] if e.source in ('OCR','VISION') else []
            if len(matches)>1:warnings.append('ambiguous_fusion')
            if e.state.get('enabled') is not True or e.state.get('offscreen') is not False:warnings.append('actionability_unverified')
            nodes.append(SceneElement(f'{obs}:{i}',e.role,e.name,e.bbox,[e],list(e.relations),warnings))
    return UISceneGraph(obs,{'hwnd':app.get('hwnd'),'pid':app.get('pid'),'process_name':app.get('process_name'),
        'process_started':app.get('process_started')},timestamp,frame,nodes)

@dataclass
class Experience:
    observation_id: str
    hypothesis: str
    authorized_action: dict | None = None
    effect: dict | None = None
    goal_check: dict | None = None
    rejected_reason: str | None = None
    def candidate(self):
        verified=(self.authorized_action is not None and self.authorized_action.get('authorized') is True and
            self.authorized_action.get('executed') is True and self.effect is not None and self.effect.get('observed') is True and
            self.goal_check is not None and self.goal_check.get('verified') is True and self.rejected_reason is None)
        return {'observation_id':self.observation_id,'hypothesis':self.hypothesis,'authorized_action':self.authorized_action,
            'effect':self.effect,'goal_check':self.goal_check,'rejected_reason':self.rejected_reason,
            'learning_candidate':verified,'pdag_write_performed':False}
