"""Maya scene adapter. All writes use native undoable Maya commands."""
from contextlib import contextmanager
import json
import math
import re

from maya import cmds
from maya.api import OpenMaya as om
from . import core


@contextmanager
def undo_chunk(label):
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya undo before editing normals')
    cmds.undoInfo(openChunk=True, chunkName=label)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def _triple(value):
    return (value.x, value.y, value.z)


def mesh_path(name):
    selection = om.MSelectionList()
    selection.add(name)
    path = selection.getDagPath(0)
    if not path.node().hasFn(om.MFn.kMesh):
        shapes = cmds.listRelatives(name, shapes=True, noIntermediate=True,
                                    fullPath=True, type='mesh') or []
        if len(shapes) != 1:
            raise ValueError('Choose a transform with exactly one polygon mesh')
        selection = om.MSelectionList()
        selection.add(shapes[0])
        path = selection.getDagPath(0)
    if path.isInstanced():
        raise ValueError('Make the mesh unique before editing normals')
    if cmds.getAttr(path.fullPathName() + '.intermediateObject'):
        raise ValueError('Intermediate meshes are not supported')
    return path


def capture(name):
    path = mesh_path(name)
    fn = om.MFnMesh(path)
    points = [_triple(p) for p in fn.getPoints(om.MSpace.kObject)]
    faces = [list(fn.getPolygonVertices(i)) for i in range(fn.numPolygons)]
    normals = [_triple(fn.getFaceVertexNormal(f, v, om.MSpace.kObject))
               for f, vertices in enumerate(faces) for v in vertices]
    face_normals = [_triple(fn.getPolygonNormal(f, om.MSpace.kObject))
                    for f in range(fn.numPolygons)]
    return core.Mesh(points, faces, normals, face_normals)


def selected_mesh():
    selected = cmds.ls(selection=True, objectsOnly=True, long=True) or []
    shapes = {mesh_path(item).fullPathName() for item in selected}
    if len(shapes) != 1:
        raise ValueError('Select components on exactly one polygon mesh')
    return shapes.pop()


def selected_corners(shape, mesh, individual=True, items=None, allow_empty=False):
    if items is None:
        items = cmds.ls(selection=True, long=True, flatten=True) or []
    converted = (cmds.polyListComponentConversion(items, toVertexFace=True) or []) if items else []
    corners = (cmds.ls(converted, long=True, flatten=True) or []) if converted else []
    lookup = {(f, v): i for i, (f, v) in enumerate(zip(mesh.corner_faces, mesh.corner_vertices))}
    result = set()
    for component in corners:
        match = re.fullmatch(r'(.+)\.vtxFace\[(\d+)\]\[(\d+)\]', component)
        if match and mesh_path(match[1]).fullPathName() == shape:
            vertex, face = int(match[2]), int(match[3])
            if (face, vertex) in lookup:
                result.add(lookup[face, vertex])
    if not individual:
        result = {i for j in result for i in mesh.vertex_corners[mesh.corner_vertices[j]]}
    if not result and not allow_empty:
        raise ValueError('Select mesh vertices, edges, faces, or vertex-faces')
    return result


def component(shape, mesh, index):
    return '{}.vtxFace[{}][{}]'.format(shape, mesh.corner_vertices[index], mesh.corner_faces[index])


def write_normals(shape, mesh, normals, lock_states=None):
    """Caller owns undo chunk. Maya commands retain original normal/lock state.

    Normals explicitly edited by this tool are frozen. For restoring a session,
    lock_states overrides that policy. Smoothing/edge flags are never changed.
    """
    if len(normals) != len(mesh.normals):
        raise ValueError('Normal count does not match topology')
    for i, (old, new) in enumerate(zip(mesh.normals, normals)):
        if not all(math.isfinite(v) for v in new) or core.dot(new, new) < core.EPSILON:
            raise ValueError('Invalid normal at corner {}'.format(i))
    for i, (old, new) in enumerate(zip(mesh.normals, normals)):
        if lock_states is None and max(abs(a-b) for a, b in zip(old, new)) < 1e-7:
            continue
        item = component(shape, mesh, i)
        cmds.polyNormalPerVertex(item, unFreezeNormal=True)
        cmds.polyNormalPerVertex(item, xyz=tuple(new))
        if lock_states is None or lock_states[i]:
            cmds.polyNormalPerVertex(item, freezeNormal=True)


def _space_matrix(path, space):
    if space == 'Object':
        return om.MMatrix()
    matrix = path.inclusiveMatrix()
    if space == 'View':
        from maya.api import OpenMayaUI as omui
        camera = omui.M3dView.active3dView().getCamera()
        matrix = matrix * camera.inclusiveMatrixInverse()
    return matrix


def _normal(n, matrix):
    return _triple(om.MVector(*n).transformAsNormal(matrix).normal())


class Session:
    def __init__(self, shape=None):
        shape = shape or selected_mesh()
        path = mesh_path(shape)
        self.uuid = cmds.ls(path.fullPathName(), uuid=True)[0]
        self.original = capture(shape)
        self.signature = self.original.signature
        fn = om.MFnMesh(path)
        _, ids = fn.getNormalIds()
        self.locks = [fn.isNormalLocked(i) for i in ids]
        self.weights = None
        self.clipboard = []
        self.mirrors = {}
        self.position_signature = tuple(self.original.points)
        self.closed = False

    @property
    def shape(self):
        if self.closed:
            raise RuntimeError('Start a new editing session')
        matches = cmds.ls(self.uuid, long=True) or []
        if len(matches) != 1:
            raise RuntimeError('The session mesh was removed or became ambiguous')
        path = mesh_path(matches[0])
        return path.fullPathName()

    def current(self):
        mesh = capture(self.shape)
        if mesh.signature != self.signature:
            raise RuntimeError('Mesh topology changed. Finish and start a new session.')
        positions = tuple(mesh.points)
        if positions != self.position_signature:
            self.mirrors.clear()
            self.position_signature = positions
        return mesh

    def select(self, individual=True):
        mesh = self.current()
        return mesh, selected_corners(self.shape, mesh, individual)

    def apply(self, operation, individual=True, space='Object', auto_mirror=(), baseline=None, **options):
        mesh, selected = self.select(individual)
        source_normals = mesh.normals if baseline is None else baseline
        if len(source_normals) != len(mesh.normals):
            raise ValueError('Drag baseline topology no longer matches')
        path = mesh_path(self.shape)
        matrix = _space_matrix(path, space)
        if abs(matrix.det4x4()) < 1e-12:
            raise ValueError('Mesh/camera transform is singular (zero scale)')
        working = core.Mesh([_triple(om.MPoint(*p) * matrix) for p in mesh.points],
                            mesh.faces, [_normal(n, matrix) for n in source_normals],
                            [_normal(n, matrix) for n in mesh.face_normals])
        if operation in ('point', 'sphere'):
            target = options.pop('target')
            target = om.MPoint(*target) * path.inclusiveMatrixInverse() * matrix
            options['target'] = _triple(target)
        reference = [_normal(n, matrix) for n in self.original.normals]
        result = core.edit(working, selected, operation, individual=individual,
                           reference=reference, weights=self.weights, **options)
        result = [_normal(n, matrix.inverse()) for n in result]
        for axis in auto_mirror:
            result = core.mirror(result, selected, self._mirror_map(mesh, axis), axis)
        with undo_chunk('Abnormal ' + operation):
            write_normals(self.shape, mesh, result)

    def _mirror_map(self, mesh, axis, tolerance=None):
        key = (axis, tolerance)
        if key not in self.mirrors:
            self.mirrors[key] = core.mirror_map(mesh, axis, tolerance)
        return self.mirrors[key]

    def mirror(self, axis, individual=True, tolerance=None):
        mesh, selected = self.select(individual)
        mapping = self._mirror_map(mesh, axis, tolerance)
        if not any(i in mapping for i in selected):
            raise ValueError('No symmetry match within the specified tolerance')
        result = core.mirror(mesh.normals, selected, mapping, axis)
        # Explicit mirror, like source auto symmetry, writes destinations.
        with undo_chunk('Abnormal mirror'):
            write_normals(self.shape, mesh, result)

    def store(self, individual=True):
        mesh, selected = self.select(individual)
        items = cmds.ls(selection=True, long=True, flatten=True) or []
        if len(items) != 1:
            raise ValueError('Store: select exactly one vertex or one vertex-face')
        last = items[0]
        if '.vtxFace[' in last:
            match = re.search(r'vtxFace\[(\d+)\]\[(\d+)\]', last)
            v, f = map(int, match.groups())
            source = [i for i in selected if mesh.corner_vertices[i] == v and mesh.corner_faces[i] == f]
        else:
            converted = cmds.ls(cmds.polyListComponentConversion(last, toVertex=True), flatten=True) or []
            if len(converted) != 1:
                raise ValueError('Store: select exactly one vertex or one vertex-face')
            vertex = int(re.search(r'vtx\[(\d+)\]', converted[0]).group(1))
            source = list(mesh.vertex_corners[vertex])
        self.clipboard = source

    def paste(self, individual=True):
        mesh, selected = self.select(individual)
        result = core.paste(mesh, selected, self.clipboard)
        result = core.blend(mesh.normals, result, selected, self.weights)
        with undo_chunk('Abnormal paste'):
            write_normals(self.shape, mesh, result)

    def mask_selection(self, individual=True):
        _, selected = self.select(individual)
        self.weights = {i: 1.0 for i in selected}

    def mask_soft_selection(self):
        mesh = self.current()
        rich = om.MGlobal.getRichSelection()
        selection = rich.getSelection()
        weights = {}
        iterator = om.MItSelectionList(selection, om.MFn.kMeshVertComponent)
        while not iterator.isDone():
            path, obj = iterator.getComponent()
            if path.fullPathName() == self.shape:
                fn = om.MFnSingleIndexedComponent(obj)
                for offset, vertex in enumerate(fn.getElements()):
                    weight = fn.weight(offset).influence if fn.hasWeights else 1.0
                    for corner in mesh.vertex_corners[vertex]:
                        weights[corner] = weight
            iterator.next()
        if not weights:
            raise ValueError('Select mesh vertices; enable soft selection for falloff weights')
        self.weights = weights

    def restore(self):
        mesh = self.current()
        with undo_chunk('Abnormal cancel session'):
            write_normals(self.shape, mesh, self.original.normals, self.locks)
        self.closed = True

    def save_vectors(self):
        mesh = self.current()
        data = json.dumps({'version': 1, 'space': 'object', 'signature': self.signature,
                           'normals': mesh.normals}, separators=(',', ':'))
        plug = self.shape + '.abnormalNormals'
        with undo_chunk('Abnormal store vectors'):
            if not cmds.objExists(plug):
                cmds.addAttr(self.shape, longName='abnormalNormals', dataType='string')
            cmds.setAttr(plug, data, type='string')

    def load_vectors(self):
        mesh = self.current()
        plug = self.shape + '.abnormalNormals'
        if not cmds.objExists(plug):
            raise ValueError('No stored abnormalNormals attribute on this mesh')
        data = json.loads(cmds.getAttr(plug))
        if data.get('version') != 1 or data.get('space') != 'object' or data.get('signature') != json.loads(json.dumps(self.signature)):
            raise ValueError('Stored normal data does not match this topology/version')
        values = data['normals']
        if len(values) != len(mesh.normals) or any(len(v) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v) or core.dot(v, v) < core.EPSILON for v in values):
            raise ValueError('Stored normal data contains invalid vectors')
        result = [core.unit(v) for v in values]
        with undo_chunk('Abnormal load vectors'):
            write_normals(self.shape, mesh, result)

    def colors(self, export=True, color_set='abnormalNormals'):
        mesh = self.current()
        fn = om.MFnMesh(mesh_path(self.shape))
        existing = fn.getColorSetNames()
        old_set = fn.currentColorSetName() if existing else None
        if not export and color_set not in existing:
            raise ValueError('The abnormalNormals color set does not exist')
        values = None
        if not export:
            values = [core.unit(tuple(fn.getFaceVertexColor(f, v, color_set))[:3], mesh.normals[i])
                      for i, (f, v) in enumerate(zip(mesh.corner_faces, mesh.corner_vertices))]
        with undo_chunk('Abnormal normal colors'):
            if export:
                if color_set not in existing:
                    cmds.polyColorSet(self.shape, create=True, colorSet=color_set, representation='RGBA', clamped=False)
                else:
                    cmds.polyColorSet(self.shape, edit=True, colorSet=color_set, clamped=False)
                cmds.polyColorSet(self.shape, currentColorSet=True, colorSet=color_set)
                try:
                    for i, n in enumerate(mesh.normals):
                        cmds.polyColorPerVertex(component(self.shape, mesh, i), rgb=n, alpha=1.0)
                finally:
                    if old_set:
                        cmds.polyColorSet(self.shape, currentColorSet=True, colorSet=old_set)
            else:
                write_normals(self.shape, mesh, values)
