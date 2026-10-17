"""Compare the pure Maya-port algorithms against the supplied Blender source.
Run from repo root: blender -b --factory-startup --python-exit-code 1 --python maya/tests/blender_parity.py
Only source UI/mesh-write and undo callbacks are replaced; algorithm functions
run in Blender with NumPy and actual mathutils. This is not Maya validation.
"""
from pathlib import Path
import importlib
import sys
from types import SimpleNamespace as NS
import numpy as np

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root.parent))
sys.path.insert(0, str(root / 'maya' / 'AbnormalMaya' / 'scripts'))
source = importlib.import_module(root.name + '.functions_modal')
from abnormal_maya import core


def setup():
    mesh = core.Mesh([(-1,0,0),(1,0,0),(0,1,0),(0,-1,0)],
                     [[0,1,2],[1,0,3]], [(0,0,1)]*3+[(0,1,0)]*3,
                     [(0,0,1)]*2)
    def padded(groups):
        width = max(map(len, groups))
        return np.array([list(group)+[-1]*(width-len(group)) for group in groups])
    container = NS(new_norms=np.array(mesh.normals,dtype=float),
                   og_norms=np.array(mesh.normals,dtype=float),
                   cache_norms=np.array(mesh.normals,dtype=float),
                   sel_status=np.array([True,False,False,False,True,False]),
                   vert_link_ls=padded(mesh.vertex_corners),
                   vert_link_vs=padded([sorted(x) for x in mesh.neighbors]),
                   loop_faces=np.array(mesh.corner_faces),
                   face_normals=np.array(mesh.face_normals,dtype=float),
                   face_link_ls=np.array(mesh.face_corners),
                   face_link_vs=np.array(mesh.faces))
    modal = NS(_container=container, _smooth_iterations=3, _smooth_strength=.4,
               _individual_loops=True, _object_smooth=True)
    return mesh, modal


def normalize(modal):
    normals = modal._container.new_norms
    modal._container.new_norms = normals / np.linalg.norm(normals,axis=1)[:,None]


source.set_new_normals = normalize
source.add_to_undostack = lambda *args: None
source.get_selected_points = lambda m, any_selected=False: np.array([
    v for v, corners in enumerate(m._container.vert_link_ls)
    if any(m._container.sel_status[c] for c in corners if c >= 0)])

cases = [
    ('flip', lambda m: source.flip_normals(m), {}),
    ('flatten', lambda m: source.flatten_normals(m,1), {'axis':(0,1,0)}),
    ('align', lambda m: source.align_to_axis_normals(m,0,-1), {'axis':(-1,0,0)}),
    ('average_vertex', source.average_vertex_normals, {}),
    ('average', source.average_selected_normals, {}),
    ('smooth', lambda m: source.smooth_normals(m,.5), {'strength':.4,'iterations':3}),
    ('reset', source.reset_normals, {}),
    ('outside', lambda m: source.set_outside_inside(m,1), {'individual':False}),
    ('inside', lambda m: source.set_outside_inside(m,-1), {'individual':False}),
]
for operation, run_source, options in cases:
    mesh, modal = setup()
    selected = set(np.flatnonzero(modal._container.sel_status))
    expected = core.edit(mesh, selected, operation, reference=mesh.normals, **options)
    run_source(modal)
    assert np.allclose(expected,modal._container.new_norms,atol=1e-7), operation
    print('PASS source parity:', operation)
print('PASS: 9 numerical comparisons with supplied Blender source; not a Maya runtime check')

# Compare actual BMLoop.calc_tangent on convex, concave and collinear corners.
import bmesh
fixtures=[[(0,0,0),(2,0,0),(2,2,0),(0,2,0)],
          [(0,0,0),(2,0,0),(1,1,0),(2,2,0),(0,2,0)],
          [(0,0,0),(1,0,0),(2,0,0),(2,2,0),(0,2,0)]]
for points in fixtures:
    bm=bmesh.new()
    try:
        vertices=[bm.verts.new(p) for p in points]
        face=bm.faces.new(vertices);bm.normal_update()
        for loop in face.loops:
            actual=core.corner_tangent(tuple(loop.vert.co),tuple(loop.link_loop_prev.vert.co),
                                       tuple(loop.link_loop_next.vert.co),tuple(face.normal))
            assert np.allclose(actual,loop.calc_tangent(),atol=2e-6),(actual,loop.calc_tangent())
    finally: bm.free()
print('PASS: actual BMesh corner tangents on convex, concave and collinear polygons')

# Compare source edge/face loop traversal on a regular quad grid.
points=[(x,y,0) for y in range(4) for x in range(4)]
faces=[[y*4+x,y*4+x+1,(y+1)*4+x+1,(y+1)*4+x] for y in range(3) for x in range(3)]
from abnormal_maya import selection
mesh=core.Mesh(points,faces,[(0,0,1)]*36,[(0,0,1)]*9)
graph=selection.Topology(mesh)
bm=bmesh.new()
try:
    vertices=[bm.verts.new(p) for p in points]
    for face in faces: bm.faces.new([vertices[v] for v in face])
    bm.verts.index_update();bm.edges.index_update();bm.faces.index_update()
    bm.verts.ensure_lookup_table();bm.edges.ensure_lookup_table();bm.faces.ensure_lookup_table()
    for edge in bm.edges:
        endpoints=tuple(sorted(v.index for v in edge.verts))
        expected={tuple(sorted(v.index for v in bm.edges[i].verts)) for i in source.get_edge_loop(bm,edge)}
        assert graph.edge_loop(endpoints)==expected,endpoints
        assert graph.face_ring(endpoints)==set(source.get_face_loop(bm,edge)),endpoints
finally: bm.free()
print('PASS: edge loops and face rings match supplied Blender traversal on a quad grid')
