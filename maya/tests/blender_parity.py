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
