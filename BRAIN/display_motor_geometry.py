"""Pure geometry of bounded paths in a union of physical display rectangles."""
import math


def monitor_at(point, topology):
    matches=[(name,rect) for name,rect in topology if rect[0]<=point[0]<rect[2] and rect[1]<=point[1]<rect[3]]
    return matches[0] if len(matches)==1 else None


def valid_topology(topology):
    return (isinstance(topology,tuple) and 1<=len(topology)<=32
            and all(isinstance(item,tuple) and len(item)==2 and isinstance(item[0],str)
                    and isinstance(item[1],tuple) and len(item[1])==4
                    and all(type(v) is int for v in item[1])
                    and item[1][0]<item[1][2] and item[1][1]<item[1][3] for item in topology)
            and len({item[0] for item in topology})==len(topology))


def segment_covered(start,target,topology):
    if not valid_topology(topology):
        return False
    # Sample each pixel interval of the straight segment, plus the effector's
    # 15 interpolated positions. Reject gaps and overlapping display ambiguity.
    n=max(1,math.ceil(math.dist(start,target)))
    if n>150:
        return False
    return all(monitor_at((round(start[0]+(target[0]-start[0])*i/count),
                           round(start[1]+(target[1]-start[1])*i/count)),topology)
               is not None for count in (n,15) for i in range(count+1))


def route(start,target,topology):
    if not valid_topology(topology) or monitor_at(start,topology) is None or monitor_at(target,topology) is None:
        raise ValueError('DISPLAY_TOPOLOGY_INVALID')
    # Candidate bends at shared vertical/horizontal boundaries allow a path
    # around missing display area. Do not route through disconnected monitors.
    nodes=[start,target]
    for i,(_,a) in enumerate(topology):
        for _,b in topology[i+1:]:
            if a[2]==b[0] or b[2]==a[0]:
                lo,hi=max(a[1],b[1]),min(a[3],b[3])
                if lo<hi:
                    x=a[2] if a[2]==b[0] else b[2]
                    y=(lo+hi-1)//2
                    nodes.extend([(x-1,y),(x,y)])
            if a[3]==b[1] or b[3]==a[1]:
                lo,hi=max(a[0],b[0]),min(a[2],b[2])
                if lo<hi:
                    y=a[3] if a[3]==b[1] else b[3]
                    x=(lo+hi-1)//2
                    nodes.extend([(x,y-1),(x,y)])
    nodes=list(dict.fromkeys(nodes))
    def split(a,b):
        n=math.ceil(math.dist(a,b)/148)
        if n>48:
            return None
        points=list(dict.fromkeys((round(a[0]+(b[0]-a[0])*i/n),round(a[1]+(b[1]-a[1])*i/n)) for i in range(1,n+1))) if n else []
        return points if all(segment_covered(x,y,topology) for x,y in zip([a]+points,points)) else None
    import heapq
    heap=[(0,0,start,[])]
    seen=set()
    sequence=0
    while heap:
        cost,_,current,path=heapq.heappop(heap)
        if current in seen:
            continue
        seen.add(current)
        if current==target:
            return path
        for other in nodes:
            if other in seen:
                continue
            points=split(current,other)
            if points is not None and len(path)+len(points)<=48:
                sequence+=1
                heapq.heappush(heap,(cost+math.dist(current,other),sequence,other,path+points))
    raise ValueError('NO_CONNECTED_DISPLAY_PATH')
