import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import nullcontext
from perception_eye import PerceptionEye
from contextual_grounder import ContextualGrounder,parse_click

class UIAReadTests(unittest.TestCase):
 def test_current_properties_no_com_proxy(self):
  p=Mock();p.pattern=object()
  control=SimpleNamespace(Name='Pincéis',AutomationId='brush',ControlTypeName='ButtonControl',ProcessId=77,IsEnabled=False,IsOffscreen=False,BoundingRectangle=SimpleNamespace(left=1,top=2,right=10,bottom=20),GetRuntimeId=lambda:[7,8],GetInvokePattern=lambda:p,GetExpandCollapsePattern=lambda:None)
  root=SimpleNamespace(Exists=lambda *args:True)
  fake=SimpleNamespace(UIAutomationInitializerInThread=lambda:nullcontext(),ControlFromHandle=lambda hwnd:root,WalkTree=lambda *a,**k:[(control,1)])
  with patch('perception_eye.auto',fake),patch('perception_eye.HAS_UIA_NATIVE',True):
   eye=PerceptionEye.__new__(PerceptionEye);item=eye.scan_uia_properties(4)[0]
  self.assertEqual(item['runtime_id'],(7,8));self.assertIs(item['is_enabled'],False);self.assertIs(item['is_offscreen'],False)
  self.assertIs(item['invoke_supported'],True);self.assertIsNone(item['expand_collapse_supported'])
 def test_disabled_and_offscreen_never_dispatch(self):
  ctx={'hwnd':11,'pid':77,'process_name':'mspaint.exe'};sensor=SimpleNamespace(capture_foreground_context=lambda:ctx)
  for enabled,offscreen,reason in [(False,False,'desabilitado'),(True,True,'fora da tela')]:
   eye=SimpleNamespace(scan_window_controls=lambda hwnd:[SimpleNamespace(name='Pincéis')],scan_uia_properties=lambda hwnd:[{'name':'Pincéis','process_id':77,'is_enabled':enabled,'is_offscreen':offscreen}])
   g=ContextualGrounder(sensor,eye,lambda pid:1);self.assertTrue(g.remember('paint','abra paint','CONCLUIDO'))
   r=g.resolve(parse_click('clique em pincéis'));self.assertEqual(r['status'],'ACTION_BLOCKED');self.assertIn(reason,r['reason'])
if __name__=='__main__':unittest.main()
