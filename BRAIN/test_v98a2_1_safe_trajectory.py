import unittest
from capability_lab import prepare_safe_trajectory

class SafeTrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.obs = {'cursor_status':'OK','interactive_desktop_verified':True,'cursor':(10,10), 'cursor_monitor':{'work_rect':(-100,-100,200,200)},'source':'mock','timestamp':1}
    def run_proposal(self, **kwargs):
        opts={'task_id':'task-1','observation':self.obs,'lab_hwnd':123,'safe_rect':(0,0,100,100),'controls_rects':[], 'dpi_verified':True,'lab_verified':True}
        opts.update(kwargs)
        return prepare_safe_trajectory(**opts)
    def test_safe_needs_authorization(self):
        r=self.run_proposal(); self.assertEqual(r['status'],'AWAITING_AUTHORIZATION'); self.assertEqual(r['target'],(40,10)); self.assertEqual(r['authorization'],'NOT_GRANTED')
    def test_missing_dpi(self): self.assertEqual(self.run_proposal(dpi_verified=False)['status'],'NOT_READY')
    def test_missing_controls(self): self.assertEqual(self.run_proposal(controls_rects=None)['status'],'NOT_READY')
    def test_intersection(self): self.assertEqual(self.run_proposal(controls_rects=[(20,0,30,20)])['status'],'NOT_READY')
    def test_outside_region(self): self.assertEqual(self.run_proposal(safe_rect=(50,0,100,100))['status'],'NOT_READY')
    def test_endpoint_outside(self): self.assertEqual(self.run_proposal(safe_rect=(0,0,40,100))['status'],'NOT_READY')
    def test_negative_coordinates(self):
        self.obs['cursor']=(-50,-20)
        self.assertEqual(self.run_proposal(safe_rect=(-80,-40,0,0))['target'],(-20,-20))
    def test_desktop_unverified(self):
        self.obs['interactive_desktop_verified']=False
        self.assertEqual(self.run_proposal()['status'],'NOT_READY')

if __name__ == '__main__': unittest.main()
