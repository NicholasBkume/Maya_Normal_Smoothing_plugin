"""Integration smoke test. Run with mayapy, or exec in Maya's Script Editor.

Creates/deletes only its own test objects, preserves selection, never resets
or saves the user's scene. Raises on failure and prints PASS only at the end.
"""
import math
import sys
from pathlib import Path

# For mayapy /path/to/maya/tests/maya_smoke.py, resolve the module automatically.
if '__file__' in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'AbnormalMaya' / 'scripts'))
try:
    from maya import cmds
    cmds.about(version=True)
except (ImportError, RuntimeError):
    import maya.standalone
    maya.standalone.initialize(name='python')
    from maya import cmds
from maya.api import OpenMaya as om
from abnormal_maya import scene, core


def close(a, b, tolerance=2e-4):
    assert len(a) == len(b)
    for va, vb in zip(a, b):
        assert all(abs(x-y) < tolerance for x, y in zip(va, vb)), (va, vb)


def locks(shape):
    fn = om.MFnMesh(scene.mesh_path(shape))
    _, ids = fn.getNormalIds()
    return [fn.isNormalLocked(i) for i in ids]


def run():
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Smoke test requires Maya undo enabled')
    previous = cmds.ls(selection=True, long=True) or []
    created = None
    try:
        created = cmds.polyCube(name='abnormalSmoke#', constructionHistory=False)[0]
        shape = scene.mesh_path(created).fullPathName()
        cmds.select(created, replace=True)
        session = scene.Session()
        original = scene.capture(shape)
        original_locks = locks(shape)
        corner = scene.component(shape, original, 0)
        cmds.select(corner, replace=True)
        session.apply('flip')
        flipped = scene.capture(shape)
        close([flipped.normals[0]], [core.mul(original.normals[0], -1)])
        close(flipped.normals[1:], original.normals[1:])
        cmds.undo()
        close(scene.capture(shape).normals, original.normals)
        assert locks(shape) == original_locks, 'Undo did not restore normal locks'
        cmds.redo()
        close(scene.capture(shape).normals, flipped.normals)
        cmds.undo()
        # Explicit empty mask must protect every corner.
        session.weights = {}
        session.apply('align', axis=(0,1,0))
        close(scene.capture(shape).normals, original.normals)
        session.weights = None
        # Test inverse-transpose world alignment under nonuniform scale.
        cmds.setAttr(created + '.scale', 2, 1, 3, type='double3')
        session.apply('align', space='World', axis=(0,1,0))
        path = scene.mesh_path(shape)
        normal = om.MVector(*scene.capture(shape).normals[0]).transformAsNormal(path.inclusiveMatrix()).normal()
        close([(normal.x,normal.y,normal.z)], [(0,1,0)])
        # Whole-mesh persistent storage round trip.
        session.save_vectors()
        stored = scene.capture(shape).normals
        session.apply('flip')
        session.load_vectors()
        close(scene.capture(shape).normals, stored)
        # Color storage must retain negative signed vector components.
        session.colors(True)
        session.apply('flip')
        session.colors(False)
        close(scene.capture(shape).normals, stored)
        # Snapshot restore includes lock state.
        session.restore()
        close(scene.capture(shape).normals, original.normals)
        assert locks(shape) == original_locks
        # Topology edits must be rejected by the old session.
        next_session = scene.Session(shape)
        cmds.polyTriangulate(shape, constructionHistory=False)
        try:
            next_session.current()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Topology change was not detected')
        print('PASS: Abnormal Maya selection, corner isolation, undo/redo, locks, masks, transforms, storage, cancel, topology guard')
    finally:
        if created and cmds.objExists(created):
            cmds.delete(created)
        surviving = [item for item in previous if cmds.objExists(item)]
        cmds.select(surviving, replace=True) if surviving else cmds.select(clear=True)


if __name__ == '__main__':
    run()
