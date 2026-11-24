from types import SimpleNamespace
from capability_lab import observe_physical_monitor
class API:
 def EnumDisplayMonitors(self):return [(1,None,None),(2,None,None)]
 def GetMonitorInfo(self,h):return {'Device':str(h)}
 def EnumDisplaySettingsEx(self,n,mode,flags):return SimpleNamespace(Position_x=-100 if n=='1' else 0,Position_y=0,PelsWidth=100,PelsHeight=100)
def test_physical_secondary():
 r=observe_physical_monitor(API(),lambda:{'status':'OBSERVED','cursor':(-30,40),'timestamp':1})
 assert r['status']=='OBSERVED' and r['monitor']=='1' and r['monitor_rect']==(-100,0,0,100)
def test_unavailable():
 assert observe_physical_monitor(API(),lambda:{'status':'OBSERVATION_UNAVAILABLE'})['status']=='OBSERVATION_UNAVAILABLE'
