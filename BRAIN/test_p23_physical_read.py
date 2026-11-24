from capability_lab import observe_physical_cursor
class API:
 def __init__(self,ok):self.ok=ok
 def GetPhysicalCursorPos(self,p):
  p._obj.x=-123;p._obj.y=45;return self.ok

def test_observation_physical_simulated():
 r=observe_physical_cursor(API(True));assert r['status']=='OBSERVED' and r['cursor']==(-123,45)

def test_observation_physical_failure():
 assert observe_physical_cursor(API(False))['status']=='OBSERVATION_UNAVAILABLE'
