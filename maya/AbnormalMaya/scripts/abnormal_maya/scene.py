"""Maya scene adapter. All writes use native undoable Maya commands."""
from contextlib import contextmanager
import json
import math
import re
from functools import wraps

from maya import cmds
from maya.api import OpenMaya as om
from . import core, display, history


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
    counts,indices=fn.getVertices()
    indices=list(indices);faces=[];offset=0
    for count in counts:
        faces.append(indices[offset:offset+count]);offset+=count
    values=fn.getNormals(om.MSpace.kObject)
    _,normal_ids=fn.getNormalIds()
    normals=[_triple(values[i]) for i in normal_ids]
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
    expanded = (cmds.ls(items, long=True, flatten=True) or []) if items else []
    # Preserve explicit face-corner membership rather than converting it via
    # vertices (which can broaden a partial corner mask).
    explicit = [item for item in expanded if '.vtxFace[' in item]
    other = [item for item in expanded if '.vtxFace[' not in item]
    converted = (cmds.polyListComponentConversion(other, toVertexFace=True) or []) if other else []
    corners = explicit + ((cmds.ls(converted, long=True, flatten=True) or []) if converted else [])
    lookup = {(f, v): i for i, (f, v) in enumerate(zip(mesh.corner_faces, mesh.corner_vertices))}
    result = set()
    resolved={}
    for component in corners:
        match = re.fullmatch(r'(.+)\.vtxFace\[(\d+)\]\[(\d+)\]', component)
        if match:
            name=match[1]
            if name not in resolved: resolved[name]=mesh_path(name).fullPathName()
        if match and resolved[match[1]] == shape:
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
        if len(new)!=3 or not all(math.isfinite(v) for v in new) or core.dot(new, new) < core.EPSILON:
            raise ValueError('Invalid normal at corner {}'.format(i))
    groups={}
    unlock=[]
    for i,(old,new) in enumerate(zip(mesh.normals,normals)):
        if lock_states is None and max(abs(a-b) for a,b in zip(old,new))<1e-7:
            continue
        item=component(shape,mesh,i)
        groups.setdefault(tuple(new),[]).append(item)
        if lock_states is not None and not lock_states[i]: unlock.append(item)
    for vector,items in groups.items():
        cmds.polyNormalPerVertex(items,normalXYZ=vector,relative=False)
    if unlock: cmds.polyNormalPerVertex(unlock,unFreezeNormal=True)
    actual = capture(shape).normals
    for i, (expected, observed) in enumerate(zip(normals, actual)):
        if max(abs(a-b) for a, b in zip(expected, observed)) > 2e-4:
            raise RuntimeError(
                'Maya normal readback failed at {}: expected {}, got {}. '
                'Use Undo to revert this operation.'.format(
                    component(shape, mesh, i), expected, observed))


def _validate_transform(path):
    # Maya can clamp zero scales in its evaluated matrix. Check the authored
    # channels too, including parents, before any inverse-normal operation.
    node = path.fullPathName()
    while node:
        if cmds.objExists(node + '.scale'):
            values = cmds.getAttr(node + '.scale')[0]
            if any(not math.isfinite(v) or v == 0.0 for v in values):
                raise ValueError('Transform is singular (zero/nonfinite scale): ' + node)
        node = node.rsplit('|', 1)[0] if '|' in node else ''


def _space_matrix(path, space):
    if space == 'Object':
        return om.MMatrix()
    matrix = path.inclusiveMatrix()
    if space == 'View':
        from maya.api import OpenMayaUI as omui
        camera = omui.M3dView.active3dView().getCamera()
        _validate_transform(camera)
        matrix = matrix * camera.inclusiveMatrixInverse()
    return matrix


def _normal(n, matrix):
    return _triple(om.MVector(*n).transformAsNormal(matrix).normal())


def recorded(function):
    @wraps(function)
    def wrapped(self,*args,**kwargs):
        self.record()
        result=function(self,*args,**kwargs)
        self.record()
        return result
    return wrapped


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
        self.original_smoothing=tuple(fn.isEdgeSmooth(i) for i in range(fn.numEdges))
        self.weights = None
        self.visibility = display.Visibility(len(self.original.normals))
        self.clipboard = []
        self.mirrors = {}
        self.position_signature = tuple(self.original.points)
        self.closed = False
        self.active_corner = None
        self.preview_selection = None
        self.history = history.History(limit=min(128,max(4,2000000//max(1,len(self.original.normals)))))
        self.record()

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
        selected = selected_corners(self.shape, mesh, individual) - self.visibility.hidden
        if not selected:
            raise ValueError('No visible selected normals. Reveal hidden normals or select others.')
        return mesh, selected

    def apply(self, operation, individual=True, space='Object', auto_mirror=(), baseline=None,
              selected_override=None,record_history=True, **options):
        if record_history: self.record()
        if selected_override is None:
            mesh, selected = self.select(individual)
        else:
            mesh=self.current()
            selected=set(selected_override)-self.visibility.hidden
            if not selected: raise ValueError('No visible normals to manipulate')
        source_normals = mesh.normals if baseline is None else baseline
        if len(source_normals) != len(mesh.normals):
            raise ValueError('Drag baseline topology no longer matches')
        path = mesh_path(self.shape)
        _validate_transform(path)
        matrix = _space_matrix(path, space)
        basis = [tuple(matrix[row*4+column] for column in range(3)) for row in range(3)]
        if core.degenerate_basis(basis):
            raise ValueError('Mesh/camera transform is singular or ill-conditioned (zero/near-zero scale)')
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
        for i in self.visibility.hidden:
            result[i] = mesh.normals[i]
        with undo_chunk('Abnormal ' + operation):
            write_normals(self.shape, mesh, result)
        if record_history: self.record()

    def snapshot(self):
        mesh=self.current()
        fn=om.MFnMesh(mesh_path(self.shape))
        _,ids=fn.getNormalIds()
        selected=(set(self.preview_selection) if self.preview_selection is not None else
                  set(selected_corners(self.shape,mesh,allow_empty=True)))-self.visibility.hidden
        return dict(normals=tuple(tuple(n) for n in mesh.normals),
                    locks=tuple(fn.isNormalLocked(i) for i in ids),
                    smoothing=tuple(fn.isEdgeSmooth(i) for i in range(fn.numEdges)),
                    selected=tuple(sorted(selected)),
                    active=self.active_corner if self.active_corner in selected else None,hidden=tuple(sorted(self.visibility.hidden)),
                    weights=None if self.weights is None else dict(self.weights),
                    clipboard=tuple(self.clipboard))

    def record(self):
        self.history.push(self.snapshot())

    def restore_snapshot(self,state):
        mesh=self.current()
        with undo_chunk('Abnormal session state'):
            write_normals(self.shape,mesh,state['normals'],state['locks'])
            self._set_smoothing(state['smoothing'])
        self.visibility._set(state['hidden'])
        self.weights=None if state['weights'] is None else dict(state['weights'])
        self.clipboard=list(state['clipboard'])
        self.active_corner=state['active']
        self._set_selection(state['selected'])

    def history_step(self,direction):
        if direction not in (-1,1): raise ValueError('History direction must be -1 or +1')
        position=self.history.position
        state=self.history.move(direction,self.snapshot())
        if state is not None:
            try: self.restore_snapshot(state)
            except Exception:
                self.history.position=position
                raise

    def _set_selection(self,indices):
        mesh=self.current()
        indices=set(indices)-self.visibility.hidden
        if not indices.issubset(range(len(mesh.normals))):
            raise ValueError('Selection contains stale corner indices')
        items=[component(self.shape,mesh,i) for i in sorted(indices)]
        cmds.select(items,replace=True) if items else cmds.select(clear=True)

    def set_selection(self,indices,active=None):
        self.record()
        self._set_selection(indices)
        self.active_corner=active if active in set(indices) else None
        self.record()

    def write_result(self,normals,record_history=True):
        if record_history: self.record()
        mesh=self.current()
        result=list(normals)
        for i in self.visibility.hidden: result[i]=mesh.normals[i]
        with undo_chunk('Abnormal manipulation'):
            write_normals(self.shape,mesh,result)
        if record_history: self.record()

    def _set_smoothing(self,flags):
        fn=om.MFnMesh(mesh_path(self.shape))
        if len(flags)!=fn.numEdges: raise ValueError('Edge smoothing topology changed')
        groups={False:[],True:[]}
        for i,smooth in enumerate(flags):
            if fn.isEdgeSmooth(i)!=bool(smooth): groups[bool(smooth)].append(self.shape+'.e[{}]'.format(i))
        for smooth,items in groups.items():
            if items: cmds.polySoftEdge(items,angle=180 if smooth else 0,constructionHistory=False)
        # A successful polySoftEdge call is not proof that edge flags changed.
        observed=om.MFnMesh(mesh_path(self.shape))
        mismatches=[i for i,expected in enumerate(flags) if observed.isEdgeSmooth(i)!=bool(expected)]
        if mismatches:
            raise RuntimeError('Edge smoothing readback failed at edges {}. Undo the operation.'.format(mismatches[:12]))

    @recorded
    def shading(self,smooth):
        mesh=self.current()
        fn=om.MFnMesh(mesh_path(self.shape))
        with undo_chunk('Abnormal shading'):
            # 0.9.1 accidentally used write_normals(mesh.normals), which skips
            # unchanged vectors and therefore NEVER froze the existing normals.
            # Maya can recalculate unlocked face-vertex normals when an edge is
            # softened/hardened. Lock them explicitly *before* polySoftEdge.
            corners=[component(self.shape,mesh,i) for i in range(len(mesh.normals))]
            if corners:
                cmds.polyNormalPerVertex(corners,freezeNormal=True)
            self._set_smoothing([smooth]*fn.numEdges)
            preserved=self.current().normals
            for i,(before,after) in enumerate(zip(mesh.normals,preserved)):
                if max(abs(a-b) for a,b in zip(before,after))>2e-4:
                    raise RuntimeError('Shading changed corner normal {}. Undo the operation.'.format(i))

    @recorded
    def copy_active(self,individual=True):
        mesh,selected=self.select(individual)
        if self.active_corner is None: raise ValueError('Pick an active normal/corner first')
        source=[self.active_corner] if individual else mesh.vertex_corners[mesh.corner_vertices[self.active_corner]]
        result=core.paste(mesh,selected,source)
        result=core.blend(mesh.normals,result,selected,self.weights)
        for i in self.visibility.hidden: result[i]=mesh.normals[i]
        with undo_chunk('Abnormal active to selection'):
            write_normals(self.shape,mesh,result)

    def _mirror_map(self, mesh, axis, tolerance=None):
        key = (axis, tolerance)
        if key not in self.mirrors:
            self.mirrors[key] = core.mirror_map(mesh, axis, tolerance)
        return self.mirrors[key]

    @recorded
    def mirror(self, axis, individual=True, tolerance=None):
        mesh, selected = self.select(individual)
        mapping = self._mirror_map(mesh, axis, tolerance)
        if not any(i in mapping for i in selected):
            raise ValueError('No symmetry match within the specified tolerance')
        result = core.mirror(mesh.normals, selected, mapping, axis)
        # Explicit mirror, like source auto symmetry, writes destinations.
        for i in self.visibility.hidden:
            result[i] = mesh.normals[i]
        with undo_chunk('Abnormal mirror'):
            write_normals(self.shape, mesh, result)

    @recorded
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

    @recorded
    def paste(self, individual=True):
        mesh, selected = self.select(individual)
        result = core.paste(mesh, selected, self.clipboard)
        result = core.blend(mesh.normals, result, selected, self.weights)
        for i in self.visibility.hidden:
            result[i] = mesh.normals[i]
        with undo_chunk('Abnormal paste'):
            write_normals(self.shape, mesh, result)

    @recorded
    def hide(self, individual=True, unselected=False):
        _, selected = self.select(individual)
        self.visibility.hide(selected, unselected=unselected)

    @recorded
    def mask_selection(self, individual=True):
        _, selected = self.select(individual)
        self.weights = {i: 1.0 for i in selected}

    @recorded
    def mask_set(self, name, individual=True):
        mesh = self.current()
        if not name or not cmds.objExists(name) or cmds.nodeType(name) != 'objectSet':
            raise ValueError('Enter an existing Maya component set')
        selection = om.MSelectionList()
        selection.add(name)
        members = om.MFnSet(selection.getDependNode(0)).getMembers(True)
        items = list(members.getSelectionStrings())
        corners = selected_corners(self.shape, mesh, individual=individual,
                                   items=items, allow_empty=True)
        self.weights = {i: 1.0 for i in corners}

    @recorded
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
            write_normals(self.shape,mesh,self.original.normals,self.locks)
            self._set_smoothing(self.original_smoothing)
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

    @recorded
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

    @recorded
    def colors(self, export=True, color_set='abnormalNormals'):
        mesh = self.current()
        fn = om.MFnMesh(mesh_path(self.shape))
        existing = fn.getColorSetNames()
        old_set = fn.currentColorSetName() if existing else None
        if not export and color_set not in existing:
            raise ValueError('The abnormalNormals color set does not exist')
        values = None
        if not export:
            # Maya exposes the plural bulk query, ordered by polygon corners.
            # getFaceVertexColor (singular) is not an MFnMesh method.
            colors = fn.getFaceVertexColors(colorSet=color_set)
            values = core.normals_from_colors(colors, len(mesh.normals))
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
