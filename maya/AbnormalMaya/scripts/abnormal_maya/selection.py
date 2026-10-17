"""Screen-space corner selection and source-style mesh traversal (no Maya)."""
from collections import deque
import math
from . import core


def distance_to_segment(point, a, b):
    delta=(b[0]-a[0],b[1]-a[1])
    length=delta[0]**2+delta[1]**2
    t=max(0,min(1,((point[0]-a[0])*delta[0]+(point[1]-a[1])*delta[1])/length)) if length else 0
    return math.hypot(point[0]-a[0]-t*delta[0],point[1]-a[1]-t*delta[1])


def in_polygon(point, polygon):
    if len(polygon)<3: return False
    inside=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if distance_to_segment(point,a,b)<1e-7: return True
        if (a[1]>point[1]) != (b[1]>point[1]):
            x=(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0]
            if point[0]<x: inside=not inside
    return inside


def choose(markers, mode, path, radius=25, tolerance=9):
    """markers: corner -> (origin2D, tip2D, wedge triangle2D).

    Region selection tests the wedge centroid (individual corner proxy).
    Clicks prefer wedge interiors, then nearest normal segment within tolerance.
    Visibility/occlusion filtering belongs to the host adapter.
    """
    if not path: return set()
    if mode=='click':
        point=path[-1]
        hits=[]
        for index,(origin,tip,wedge) in markers.items():
            if in_polygon(point,list(wedge)):
                center=core.mean([(p[0],p[1],0) for p in wedge])
                hits.append((-1,math.hypot(point[0]-center[0],point[1]-center[1]),index))
            else:
                distance=distance_to_segment(point,origin,tip)
                if distance<=tolerance: hits.append((distance,0,index))
        return {min(hits)[2]} if hits else set()
    result=set()
    for index,(origin,tip,wedge) in markers.items():
        center=(sum(p[0] for p in wedge)/3,sum(p[1] for p in wedge)/3)
        if mode=='box':
            a,b=path[0],path[-1]
            hit=min(a[0],b[0])<=center[0]<=max(a[0],b[0]) and min(a[1],b[1])<=center[1]<=max(a[1],b[1])
        elif mode=='circle':
            hit=any(math.hypot(center[0]-p[0],center[1]-p[1])<=radius for p in path)
        elif mode=='lasso': hit=in_polygon(center,list(path))
        else: raise ValueError('Unknown selection mode: '+mode)
        if hit: result.add(index)
    return result


def combine(original, hits, mode='replace'):
    original,hits=set(original),set(hits)
    if mode=='replace': return hits
    if mode=='add': return original|hits
    if mode=='subtract': return original-hits
    if mode=='toggle': return original^hits
    raise ValueError('Unknown selection combination')


class Topology:
    def __init__(self,mesh):
        self.mesh=mesh
        self.edges={}
        self.vertex_edges=[set() for _ in mesh.points]
        self.face_edges=[]
        for face,vertices in enumerate(mesh.faces):
            edges=[]
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):
                edge=tuple(sorted((a,b)))
                self.edges.setdefault(edge,set()).add(face)
                self.vertex_edges[a].add(edge)
                self.vertex_edges[b].add(edge)
                edges.append(edge)
            self.face_edges.append(edges)

    def linked(self,seeds,blocked=()):
        visited=set(seeds)-set(blocked)
        queue=deque(sorted(visited))
        while queue:
            for neighbor in sorted(self.mesh.neighbors[queue.popleft()]):
                if neighbor not in visited and neighbor not in blocked:
                    visited.add(neighbor);queue.append(neighbor)
        return visited

    def path(self,start,end,faces=False,blocked=()):
        if faces:
            adjacency=[set() for _ in self.mesh.faces]
            for connected in self.edges.values():
                for face in connected: adjacency[face].update(connected-{face})
        else: adjacency=self.mesh.neighbors
        if start<0 or end<0 or start>=len(adjacency) or end>=len(adjacency):
            raise ValueError('Path endpoint outside mesh')
        parents={start:None}; queue=deque([start]);blocked=set(blocked)-{start,end}
        while queue:
            current=queue.popleft()
            if current==end:
                result=[]
                while current is not None:
                    result.append(current);current=parents[current]
                return result[::-1]
            for neighbor in sorted(adjacency[current]):
                if neighbor not in parents and neighbor not in blocked:
                    parents[neighbor]=current;queue.append(neighbor)
        raise ValueError('No connected path between the selected endpoints')

    def edge_loop(self,edge,blocked=()):
        edge=tuple(sorted(edge))
        if edge not in self.edges: raise ValueError('Select a mesh edge')
        used={edge};blocked=set(blocked)
        for vertex in edge:
            current=edge
            while len(self.vertex_edges[vertex])==4:
                candidates=[e for e in sorted(self.vertex_edges[vertex])
                            if e not in used and not(self.edges[e]&self.edges[current])]
                if not candidates: break
                following=candidates[0]
                vertex=next(v for v in following if v!=vertex)
                if vertex in blocked: break
                used.add(following);current=following
        return used

    def face_ring(self,edge,blocked=()):
        edge=tuple(sorted(edge))
        if edge not in self.edges: raise ValueError('Select a mesh edge')
        visited=set();seen_edges={edge};queue=deque([edge]);blocked=set(blocked)
        while queue:
            current=queue.popleft()
            for face in sorted(self.edges[current]-visited-blocked):
                if len(self.mesh.faces[face])!=4: continue
                visited.add(face)
                edges=self.face_edges[face]
                opposite=edges[(edges.index(current)+2)%4]
                if opposite not in seen_edges:
                    seen_edges.add(opposite);queue.append(opposite)
        return visited


def ring_angle(start,current,center):
    a=math.atan2(start[1]-center[1],start[0]-center[0])
    b=math.atan2(current[1]-center[1],current[0]-center[0])
    return math.atan2(math.sin(b-a),math.cos(b-a))
