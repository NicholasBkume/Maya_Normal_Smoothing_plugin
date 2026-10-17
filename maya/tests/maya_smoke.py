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
if '__file__' in globals():
    expected_scripts = Path(__file__).resolve().parents[1] / 'AbnormalMaya' / 'scripts'
    if expected_scripts not in Path(scene.__file__).resolve().parents:
        raise RuntimeError('An older Abnormal Maya package is already loaded. Restart Maya before testing this version. Loaded adapter: ' + scene.__file__)


def close(a, b, tolerance=2e-4, stage='normal comparison'):
    assert len(a) == len(b), '{}: count mismatch'.format(stage)
    for index, (va, vb) in enumerate(zip(a, b)):
        assert all(abs(x-y) < tolerance for x, y in zip(va, vb)), '{}: corner {}: got {}, expected {}'.format(stage, index, va, vb)


def locks(shape):
    fn = om.MFnMesh(scene.mesh_path(shape))
    _, ids = fn.getNormalIds()
    return [fn.isNormalLocked(i) for i in ids]


def run():
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Smoke test requires Maya undo enabled')
    print('Abnormal Maya smoke — Maya {}, package {}'.format(cmds.about(version=True), __import__('abnormal_maya').__version__))
    print('Adapter:', scene.__file__)
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
        close([flipped.normals[0]], [core.mul(original.normals[0], -1)], stage='initial flip')
        close(flipped.normals[1:], original.normals[1:], stage='unselected corner isolation')
        cmds.undo()
        close(scene.capture(shape).normals, original.normals, stage='undo flip')
        assert locks(shape) == original_locks, 'Undo did not restore normal locks'
        cmds.redo()
        close(scene.capture(shape).normals, flipped.normals, stage='redo flip')
        cmds.undo()
        # Explicit empty mask must protect every corner.
        session.weights = {}
        session.apply('align', axis=(0,1,0))
        close(scene.capture(shape).normals, original.normals, stage='zero mask / restored baseline')
        session.weights = None
        # Test inverse-transpose world alignment under nonuniform scale.
        cmds.setAttr(created + '.scale', 2, 1, 3, type='double3')
        session.apply('align', space='World', axis=(0,1,0))
        path = scene.mesh_path(shape)
        normal = om.MVector(*scene.capture(shape).normals[0]).transformAsNormal(path.inclusiveMatrix()).normal()
        close([(normal.x,normal.y,normal.z)], [(0,1,0)], stage='world-space alignment')
        # Whole-mesh persistent storage round trip.
        session.save_vectors()
        stored = scene.capture(shape).normals
        session.apply('flip')
        session.load_vectors()
        close(scene.capture(shape).normals, stored, stage='JSON storage round trip')
        # Color storage must retain negative signed vector components.
        session.colors(True)
        session.apply('flip')
        session.colors(False)
        close(scene.capture(shape).normals, stored, stage='color storage round trip')
        # Snapshot restore includes lock state.
        session.restore()
        close(scene.capture(shape).normals, original.normals, stage='cancel session restore')
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
