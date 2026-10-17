"""Optional VP2 overlay controller. All Maya/Qt work happens on the main thread.

The draw plugin consumes immutable payloads and never queries the edited mesh
from the render callback. A transient locator shape is parented to the source
transform; it does not write to saved scene files (MPxNode.setDoNotWrite).
"""
from contextlib import contextmanager
from pathlib import Path
import uuid
from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaRender as omr
from . import core, display, scene

NODE_TYPE = 'abnormalNormalOverlay'
PAYLOADS = {}


@contextmanager
def transient_changes():
    # Display-only helper creation/deletion must not split a normal-edit undo
    # gesture. Never flush the user's history; restore the prior setting.
    enabled = cmds.undoInfo(query=True, state=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        yield
    finally:
        cmds.undoInfo(stateWithoutFlush=enabled)


def load_plugin():
    path = str(Path(__file__).with_name('abnormal_maya_vp2.py'))
    try:
        loaded = cmds.pluginInfo(path, query=True, loaded=True)
    except RuntimeError:
        loaded = False
    if not loaded:
        cmds.loadPlugin(path, quiet=True)


class Controller:
    def __init__(self, session):
        self.session = session
        self.key = uuid.uuid4().hex
        self.node = None
        self.node_uuid = None
        self._previous = None
        load_plugin()
        parent = cmds.listRelatives(session.shape, parent=True, fullPath=True)[0]
        try:
            with transient_changes():
                self.node = cmds.createNode(NODE_TYPE, name='abnormalNormalOverlayShape#',
                                            parent=parent, skipSelect=True)
                self.node = cmds.ls(self.node,long=True)[0]
                self.node_uuid = cmds.ls(self.node,uuid=True)[0]
                cmds.setAttr(self.node+'.overlayKey', self.key, type='string')
                cmds.setAttr(self.node+'.hiddenInOutliner', True)
                cmds.setAttr(self.node+'.overrideEnabled', True)
                cmds.setAttr(self.node+'.overrideDisplayType', 2)
        except Exception:
            self.close()
            raise

    def update(self, individual=True, xray=False, point_size=4, line_width=1.5, **options):
        mesh = self.session.current()
        self._resolve_node()
        if not self.node or not cmds.objExists(self.node):
            raise RuntimeError('Overlay helper was removed; toggle the custom overlay to recreate it')
        selected = scene.selected_corners(self.session.shape, mesh, individual,
                                         allow_empty=True) - self.session.visibility.hidden
        items = cmds.ls(selection=True,long=True,flatten=True) or []
        active = scene.selected_corners(self.session.shape, mesh, individual,
                                       items=items[-1:],allow_empty=True) if items and '.' in items[-1] else set()
        path = scene.mesh_path(self.session.shape)
        scene._validate_transform(path)
        matrix = path.inclusiveMatrix()
        basis = [tuple(matrix[r*4+c] for c in range(3)) for r in range(3)]
        if core.degenerate_basis(basis):
            raise ValueError('Cannot draw normals with a singular transform')
        world = core.Mesh([scene._triple(om.MPoint(*p)*matrix) for p in mesh.points],mesh.faces,
                          [scene._normal(n,matrix) for n in mesh.normals],
                          [scene._normal(n,matrix) for n in mesh.face_normals])
        payload = (display.batches(world, selected, active,
                                  hidden=self.session.visibility.hidden,
                                  weights=self.session.weights, **options),
                   bool(xray), float(point_size), float(line_width))
        if payload != self._previous:
            PAYLOADS[self.key] = payload
            self._previous = payload
            selection = om.MSelectionList()
            selection.add(self.node)
            omr.MRenderer.setGeometryDrawDirty(selection.getDependNode(0))
            cmds.refresh(force=True)

    def _resolve_node(self):
        if self.node_uuid:
            nodes = cmds.ls(self.node_uuid,long=True) or []
            self.node = nodes[0] if len(nodes) == 1 else None

    def close(self):
        self._resolve_node()
        PAYLOADS.pop(self.key,None)
        if self.node and cmds.objExists(self.node):
            with transient_changes():
                cmds.delete(self.node)
        self.node = None
