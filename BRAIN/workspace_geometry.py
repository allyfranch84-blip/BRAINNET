"""Compile closed integer polylines into existing bounded relative moves.
No new actuator access and no increase in the physical step budget.
"""
import math

DIRECTION = {(1,0):'right',(-1,0):'left',(0,1):'down',(0,-1):'up',
             (1,1):'down_right',(1,-1):'up_right',(-1,1):'down_left',(-1,-1):'up_left'}

def compile_polyline(vertices):
    if len(vertices)<3 or vertices[0]!=vertices[-1]:
        raise ValueError('Closed polygon required')
    steps=[]
    for (x,y),(u,v) in zip(vertices,vertices[1:]):
        dx,dy=u-x,v-y
        if not dx and not dy:raise ValueError('Empty edge')
        if dx and dy and abs(dx)!=abs(dy):raise ValueError('Unsupported edge direction')
        sx=(dx>0)-(dx<0);sy=(dy>0)-(dy<0)
        diagonal=bool(dx and dy)
        remaining=max(abs(dx),abs(dy))
        while remaining:
            part=min(106 if diagonal else 150,remaining)
            # resolve_move truncates normalized components. ceil ensures each
            # diagonal component is exactly part, rather than part-1.
            distance=math.ceil(part*math.sqrt(2)) if diagonal else part
            steps.append({'action':'move','direction':DIRECTION[sx,sy],'distance':distance})
            remaining-=part
            if len(steps)>8:raise ValueError('Physical segment budget exceeded')
    return {'status':'execute','steps':steps}

def polygon_plan(shape,size):
    if type(size) is not int or not 1<=size<=300:raise ValueError('Invalid size')
    if shape=='quadrado':vertices=[(0,0),(size,0),(size,size),(0,size),(0,0)]
    elif shape=='triangulo':vertices=[(0,0),(size,0),(0,size),(0,0)]
    else:raise ValueError('Unsupported polygon')
    return compile_polyline(vertices)
