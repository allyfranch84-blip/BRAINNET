import os,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from ui_scene_graph import build_scene_graph, Evidence, Experience
from BRAINNET import BrainnetKernel

class SceneTests(unittest.TestCase):
 def setUp(self):self.app={'pid':2,'hwnd':1,'process_name':'app.exe'};self.frame={'coordinate_space':'screen_physical','registration_id':'frame1'}
 def uia(self,name='Play',rect=(10,10,40,40),enabled=True):return {'name':name,'rect':rect,'control_type':'ButtonControl','is_enabled':enabled,'is_offscreen':False,'invoke_supported':True,'runtime_id':(1,2)}
 def visual(self,name='Play',rect=(10,10,40,40),role='button',**state):return {'name':name,'bbox':rect,'role':role,'coordinate_space':'screen_physical','registration_id':'frame1','confidence':.6,'state':state,'interactions':['CLICK']}
 def graph(self,**kw):return build_scene_graph(app=self.app,frame=self.frame,**kw)
 def test_uia_control_is_not_authorized(self):
  node=self.graph(uia=[self.uia()]).elements[0].to_dict();self.assertIn('CLICK',node['possible_interactions']);self.assertFalse(node['action_authorized'])
 def test_visual_only_is_hypothesis(self):
  e=self.graph(visual=[self.visual()]).elements[0];self.assertIn('visual_or_ocr_hypothesis',e.uncertainty);self.assertFalse(e.evidence[0].verified)
 def test_canvas_no_internal_uia(self):
  e=self.graph(visual=[self.visual('canvas',role='canvas')]).elements[0];self.assertEqual(e.role,'canvas');self.assertFalse(e.to_dict()['action_authorized'])
 def test_dom_preferred_on_matching_frame(self):
  d={**self.visual(),'state':{'enabled':True},'reference':'button-1'};g=self.graph(uia=[self.uia()],dom=[d]);self.assertEqual(len(g.elements),1);self.assertEqual(g.elements[0].evidence[0].source,'DOM')
 def test_fusion_preserves_contradictions(self):
  g=self.graph(uia=[self.uia(enabled=False)],visual=[self.visual(enabled=True)]);self.assertEqual(len(g.elements),1);self.assertIn('conflicting_enabled',g.elements[0].uncertainty);self.assertEqual(len(g.elements[0].evidence),2)
 def test_duplicate_or_ambiguous_not_merged(self):
  g=self.graph(uia=[self.uia(),self.uia()],visual=[self.visual()]);self.assertEqual(len(g.elements),3)
 def test_ambiguous_visual_targets_are_not_resolved_to_one(self):
  g=self.graph(visual=[self.visual('Menu',(10,10,40,40)),self.visual('Menu',(50,10,80,40))])
  self.assertEqual(len(g.find('Menu')),2)
 def test_mismatched_registration_not_merged(self):
  v=self.visual();v['registration_id']='other';g=self.graph(uia=[self.uia()],visual=[v]);self.assertEqual(len(g.elements),2)
 def test_layout_and_temporal_invalidation(self):
  a=self.graph(uia=[self.uia()],observed_at=10);b=self.graph(uia=[self.uia(rect=(50,50,80,80))],observed_at=12)
  self.assertNotEqual(a.observation_id,b.observation_id);self.assertFalse(a.valid_for(hwnd=1,pid=2,now=20))
  self.assertFalse(a.valid_for(hwnd=1,pid=2,now=11,observation_id=b.observation_id,process_started=123))
 def test_dpi_coordinates_do_not_mix(self):
  v=self.visual(rect=(5,5,20,20));v['coordinate_space']='css_pixels';self.assertEqual(len(self.graph(uia=[self.uia()],visual=[v]).elements),2)
 def test_disabled_control_is_not_clickable_proof(self):
  e=self.graph(uia=[self.uia(enabled=False)]).elements[0];self.assertIn('actionability_unverified',e.uncertainty)
 def test_failure_sources_optional(self):
  self.assertEqual(len(self.graph(ocr=[],visual=[]).elements),0)
 def test_same_concept_two_apps(self):
  a=self.graph(uia=[self.uia('Volume')]);b=build_scene_graph(app={'pid':5,'hwnd':6},frame=self.frame,visual=[self.visual('Volume')]);self.assertEqual(a.elements[0].role,b.elements[0].role)
 def test_experience_no_learning_without_facts(self):
  x=Experience('obs','click');self.assertFalse(x.candidate()['learning_candidate']);x.rejected_reason='blocked';self.assertFalse(x.candidate()['pdag_write_performed'])
 def test_three_synthetic_apps(self):
  fixtures={'paint':[self.visual('Pincéis')],'youtube':[self.visual('Reproduzir'),self.visual('Volume',(50,10,80,40))],'editor':[self.visual('Exposição',role='slider')]}
  for app,els in fixtures.items():
   with self.subTest(app=app):self.assertEqual(len(self.graph(visual=els).elements),len(els))
 def test_kernel_optin(self):
  k=BrainnetKernel.__new__(BrainnetKernel);k.context_engine=Mock();k.eye=Mock()
  with patch.dict(os.environ,{},clear=True):self.assertEqual(k.observe_ui_scene()['status'],'DISABLED');k.context_engine.capture_foreground_context.assert_not_called()
 def test_kernel_uia_read_only(self):
  k=BrainnetKernel.__new__(BrainnetKernel);k.context_engine=Mock();k.eye=Mock();k.context_engine.capture_foreground_context.return_value=self.app;k.eye.scan_uia_properties.return_value=[self.uia()]
  with patch.dict(os.environ,{'BRAINNET_UI_SCENE_OBSERVE':'1'},clear=True),patch('psutil.Process') as p:
   p.return_value.create_time.return_value=123;r=k.observe_ui_scene();self.assertEqual(r['status'],'OBSERVED');self.assertEqual(len(r['scene']['elements']),1)
 def test_observation_context_changed(self):
  k=BrainnetKernel.__new__(BrainnetKernel);k.context_engine=Mock();k.eye=Mock();k.context_engine.capture_foreground_context.side_effect=[self.app,{'hwnd':4,'pid':2}];k.eye.scan_uia_properties.return_value=[]
  with patch.dict(os.environ,{'BRAINNET_UI_SCENE_OBSERVE':'1'},clear=True),patch('psutil.Process') as p:
   p.return_value.create_time.return_value=123;self.assertEqual(k.observe_ui_scene()['status'],'CONTEXT_CHANGED')
if __name__=='__main__':unittest.main()
