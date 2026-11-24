"""Cross-display geometry tests, no native input."""
import math
import pytest
from display_motor_geometry import route, segment_covered, monitor_at

TOPOLOGY=(('DISPLAY1',(0,0,1920,1080)),('DISPLAY2',(1920,0,3520,900)))

def test_connected_displays():
    start=(947,685)
    target=(3416,843)
    points=route(start,target,TOPOLOGY)
    assert points[-1]==target
    assert all(0<math.dist(a,b)<=150 and segment_covered(a,b,TOPOLOGY) for a,b in zip([start]+points,points))
    assert monitor_at(points[-1],TOPOLOGY)[0]=='DISPLAY2'

def test_avoid_unoccupied_area_below_second_monitor():
    start=(1900,1050)
    target=(3400,850)
    points=route(start,target,TOPOLOGY)
    assert points[-1]==target
    assert all(segment_covered(a,b,TOPOLOGY) for a,b in zip([start]+points,points))

def test_negative_origin_and_vertical_layout():
    topology=(('LEFT',(-1600,0,0,900)),('RIGHT',(0,0,1920,1080)),('TOP',(0,-800,1280,0)))
    start=(-50,800)
    target=(200,-700)
    points=route(start,target,topology)
    assert points[-1]==target
    assert all(segment_covered(a,b,topology) for a,b in zip([start]+points,points))

def test_disconnected_displays_block():
    with pytest.raises(ValueError):
        route((10,10),(220,10),(('A',(0,0,100,100)),('B',(200,0,300,100))))
