from parser_contract import parse_supervised_mouse_move
from capability_lab import propose_delegated_move
from test_v97r22_production import make_bridge

def test_delegated_intent_does_not_authorize():
    p=parse_supervised_mouse_move('mova o mouse em qualquer direção')
    assert p['direction_delegated'] and p['maximum_distance']==20 and not p['execution_authorized']
    r=make_bridge().send_command('mova o mouse em qualquer direção')
    assert r['status']=='ACTION_BLOCKED' and not r['dispatched']
    assert r['motor_proposal']['task_id']==r['task_budget']['task_id']

def test_monitor_edges_and_negative_coordinates():
    r=propose_delegated_move((-1,0),(-100,-100,1,100),(-100,-100,1,100),coordinates_verified=True)
    assert r['dx']==-20 and r['target']==(-21,0) and not r['execution_authorized']
    r=propose_delegated_move((0,0),(0,0,1,1),(0,0,1,1),coordinates_verified=True)
    assert r['status']=='ACTION_BLOCKED'

def test_dpi_and_invalid_geometry_fail_closed():
    assert propose_delegated_move((0,0),(-100,-100,100,100),(-100,-100,100,100))['reason']=='COORDINATE_MISMATCH'
    assert propose_delegated_move((True,0),(-100,-100,100,100),(-100,-100,100,100),coordinates_verified=True)['status']=='ACTION_BLOCKED'
