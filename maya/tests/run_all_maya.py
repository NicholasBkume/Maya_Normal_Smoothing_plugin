"""Run extended Abnormal Maya checks in Maya's PYTHON Script Editor.

Download this file, then:
    import runpy
    runpy.run_path(r'C:/path/to/run_all_maya.py')['run']()

Uses the installed package, or the scripts folder beside this distribution.
Never opens, resets, or saves the scene. Test objects are removed afterward.
Like other Maya command tests, it adds entries to the global undo history.
A modeless checklist covers real mouse gestures and visual checks that cannot
be established by calling callbacks. Close it to remove its own test objects.
"""
import json
import math
from pathlib import Path
import sys
import traceback
import time
import uuid
from unittest import mock


def run(manual=True, report_path=None):
    """Return automated results; optionally open the guided viewport checklist.

    report_path is optional: an explicit JSON path to write the automated report.
    No files are written by default. An automated FAIL raises after all cases run.
    """
    from maya import cmds
    from maya.api import OpenMaya as om
    candidate = None
    if '__file__' in globals():
        candidate = Path(__file__).resolve().parents[1] / 'AbnormalMaya' / 'scripts'
        if (candidate / 'abnormal_maya' / '__init__.py').is_file():
            sys.path.insert(0, str(candidate))
    try:
        import abnormal_maya
    except ImportError:
        if '__file__' not in globals():
            raise RuntimeError('Install Abnormal Maya first')
        scripts = Path(__file__).resolve().parents[1] / 'AbnormalMaya' / 'scripts'
        sys.path.insert(0, str(scripts))
        import abnormal_maya
    from abnormal_maya import core, scene, tools
    if candidate and candidate.is_dir() and candidate not in Path(scene.__file__).resolve().parents:
        raise RuntimeError('An older Abnormal Maya is cached. Restart Maya and run this file again. Loaded: ' + scene.__file__)
    if not hasattr(scene.Session, 'history_step'):
        raise RuntimeError('This runner requires Abnormal Maya 0.9.5. Download the new package and restart Maya.')
    from abnormal_maya import overlay
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya undo before running these tests')
    if tools._INTERACTION is not None:
        raise RuntimeError('Exit corner picking or confirm/cancel the live tool before running tests')
    if tools._TOOL is not None and cmds.currentCtx() == tools._CONTEXT:
        raise RuntimeError('Exit the Abnormal rotation tool with Q before running tests')
    previous_selection = cmds.ls(selection=True, long=True) or []
    previous_tool = cmds.currentCtx()
    soft_enabled = cmds.softSelect(query=True, softSelectEnabled=True)
    soft_distance = cmds.softSelect(query=True, softSelectDistance=True)
    soft_falloff = cmds.softSelect(query=True, softSelectFalloff=True)
    previous_tool_object = tools._TOOL
    previous_context_name = tools._CONTEXT
    suffix = uuid.uuid4().hex[:10]
    # Exercise the real native context under a unique test-only name.
    # Existing user contexts are neither deleted nor replaced.
    validation_context_name = 'abnormalValidationRotateContext_' + suffix
    preexisting_context = False
    root = cmds.group(empty=True, name='abnormalValidation_' + suffix)
    tools._CONTEXT = validation_context_name
    owned_sets = []
    owned_panels = []
    cases = []
    results = []

    class Skip(Exception):
        pass

    def check(condition, message):
        if not condition:
            raise AssertionError(message)

    def vectors(actual, expected, label='normal comparison'):
        check(len(actual) == len(expected), label + ': count mismatch')
        for index, (a, b) in enumerate(zip(actual, expected)):
            check(max(abs(x-y) for x, y in zip(a, b)) < 3e-4,
                  '{} corner {}: got {}, expected {}'.format(label, index, a, b))

    def fixture():
        cube = cmds.polyCube(name='abnormalCase_' + suffix + '#', constructionHistory=False)[0]
        cube = cmds.parent(cube, root)[0]
        shape = scene.mesh_path(cube).fullPathName()
        cmds.select(shape, replace=True)
        session = scene.Session(shape)
        mesh = session.current()
        cmds.select(scene.component(shape, mesh, 0), replace=True)
        return cube, shape, session, mesh

    def selected(shape, mesh, indices):
        values = [scene.component(shape, mesh, i) for i in indices]
        cmds.select(values, replace=True) if values else cmds.select(clear=True)

    def expect_error(callback, phrase=None):
        try:
            callback()
        except (ValueError, RuntimeError) as exc:
            if phrase:
                check(phrase.lower() in str(exc).lower(), str(exc))
        else:
            raise AssertionError('Expected a clear rejection')

    def case(name):
        def register(fn):
            cases.append((name, fn))
            return fn
        return register

    @case('All normal operation buttons: object-space results')
    def numerical_operations():
        for operation in ('flip','flatten','align','rotate','average','average_vertex',
                          'smooth','from_faces','inside','outside','point','sphere','reset'):
            _, shape, session, mesh = fixture()
            indices = set(mesh.face_corners[0])
            selected(shape, mesh, indices)
            options = dict(axis=(1,0,0), angle=math.radians(35), strength=.4, iterations=2)
            if operation in ('point','sphere'):
                options['target'] = (2,3,4)
            expected = core.edit(mesh, indices, operation, reference=mesh.normals, **options)
            session.apply(operation, **options)
            vectors(scene.capture(shape).normals, expected, operation)

    @case('Normal undo, redo, corner isolation and lock restoration')
    def history():
        _, shape, session, mesh = fixture()
        fn = om.MFnMesh(scene.mesh_path(shape))
        _, ids = fn.getNormalIds()
        before_locks = [fn.isNormalLocked(i) for i in ids]
        session.apply('flip')
        expected = list(mesh.normals)
        expected[0] = core.mul(expected[0], -1)
        vectors(scene.capture(shape).normals, expected, 'flip')
        cmds.undo()
        vectors(scene.capture(shape).normals, mesh.normals, 'undo')
        fn = om.MFnMesh(scene.mesh_path(shape))
        _, ids = fn.getNormalIds()
        check([fn.isNormalLocked(i) for i in ids] == before_locks, 'Undo changed normal locks')
        cmds.redo()
        vectors(scene.capture(shape).normals, expected, 'redo')
        session.restore()
        vectors(scene.capture(shape).normals, mesh.normals, 'cancel')
        check(session.closed, 'Cancel did not close the session')

    @case('World-space normals under rotated, nonuniform and negative transforms')
    def transforms():
        cube, shape, session, _ = fixture()
        cmds.setAttr(cube+'.rotate', 23,41,17, type='double3')
        cmds.setAttr(cube+'.scale', -2,1,3, type='double3')
        axis = core.unit((1,2,3))
        session.apply('align', space='World', axis=axis)
        path = scene.mesh_path(shape)
        n = om.MVector(*session.current().normals[0]).transformAsNormal(path.inclusiveMatrix()).normal()
        vectors([(n.x,n.y,n.z)], [axis], 'world align')
        before = session.current().normals
        cmds.setAttr(cube+'.scaleX', 0)
        expect_error(lambda: session.apply('align', space='World'), 'singular')
        cmds.setAttr(cube+'.scaleX', -2)
        vectors(session.current().normals, before, 'singular rejection must not edit normals')

    @case('View-space rotation against active camera matrix')
    def view_space():
        if cmds.about(batch=True):
            raise Skip('Requires a Maya GUI viewport')
        from maya.api import OpenMayaUI as omui
        _, shape, session, mesh = fixture()
        path = scene.mesh_path(shape)
        view = omui.M3dView.active3dView()
        matrix = path.inclusiveMatrix() * view.getCamera().inclusiveMatrixInverse()
        old = om.MVector(*mesh.normals[0]).transformAsNormal(matrix).normal()
        rotated = core.rotate((old.x,old.y,old.z), (0,1,0), .3)
        expected = om.MVector(*rotated).transformAsNormal(matrix.inverse()).normal()
        session.apply('rotate', space='View', axis=(0,1,0), angle=.3)
        vectors([session.current().normals[0]], [(expected.x,expected.y,expected.z)], 'view rotate')

    @case('Manual symmetry, auto symmetry and distance rejection')
    def symmetry():
        _, shape, session, mesh = fixture()
        mapping = core.mirror_map(mesh, 0)
        expected = core.mirror(mesh.normals, {0}, mapping, 0)
        session.mirror(0)
        vectors(session.current().normals, expected, 'manual mirror')
        current = session.current()
        expected = core.edit(current, {0}, 'align', axis=core.unit((1,2,3)))
        expected = core.mirror(expected, {0}, mapping, 0)
        session.apply('align', axis=core.unit((1,2,3)), auto_mirror=(0,))
        vectors(session.current().normals, expected, 'auto mirror')
        # Translate points, not the transform, to break origin symmetry.
        cmds.move(10,0,0, shape+'.vtx[*]', relative=True, objectSpace=True)
        expect_error(lambda: session.mirror(0, tolerance=.001), 'No symmetry match')

    @case('Live corner clipboard and vertex clipboard')
    def clipboard():
        _, shape, session, mesh = fixture()
        session.store(True)
        source = list(session.clipboard)
        session.apply('align', axis=(1,0,0))
        current = session.current()
        selected(shape, mesh, [1,2])
        expected = core.paste(current, {1,2}, source)
        session.paste(True)
        vectors(session.current().normals, expected, 'corner paste')
        cmds.select(shape+'.vtx[0]', replace=True)
        session.store(False)
        check(set(session.clipboard) == set(mesh.vertex_corners[0]), 'Vertex clipboard lost corners')
        destination = mesh.vertex_corners[1]
        current = session.current()
        selected(shape, mesh, destination)
        expected = core.paste(current, set(destination), session.clipboard)
        session.paste(True)
        vectors(session.current().normals, expected, 'vertex tangent-matched paste')

    @case('Binary, empty and fractional weight masks')
    def masks():
        _, shape, session, mesh = fixture()
        session.mask_selection(True)
        selected(shape, mesh, [0,1])
        expected = core.edit(mesh, {0,1}, 'align', axis=(1,0,0), weights={0:1})
        session.apply('align', axis=(1,0,0))
        vectors(session.current().normals, expected, 'binary mask')
        current = session.current()
        session.weights = {}
        session.apply('flip')
        vectors(session.current().normals, current.normals, 'empty mask')
        session.weights = {0:.25, 1:.5}
        expected = core.edit(current, {0,1}, 'align', axis=(0,1,0), weights=session.weights)
        session.apply('align', axis=(0,1,0))
        vectors(session.current().normals, expected, 'fractional mask')

    @case('Native Maya soft-selection weight extraction')
    def soft_mask():
        _, shape, session, mesh = fixture()
        cmds.softSelect(softSelectEnabled=True, softSelectDistance=2.0, softSelectFalloff=0)
        cmds.select(shape+'.vtx[0]', replace=True)
        session.mask_soft_selection()
        check(session.weights is not None and bool(session.weights), 'No rich selection weights')
        check(all(0 <= value <= 1 for value in session.weights.values()), 'Weights outside 0..1')
        check(all(abs(session.weights.get(i,0)-1) < 1e-5 for i in mesh.vertex_corners[0]),
              'Selected vertex should have weight 1 at all its corners')
        cmds.softSelect(softSelectEnabled=False)

    @case('Signed color data and JSON storage round trips')
    def storage():
        _, shape, session, mesh = fixture()
        session.apply('align', axis=core.unit((-1,-2,-3)))
        expected = session.current().normals
        session.save_vectors()
        session.colors(True)
        session.apply('flip')
        session.load_vectors()
        vectors(session.current().normals, expected, 'JSON round trip')
        session.apply('flip')
        session.colors(False)
        vectors(session.current().normals, expected, 'signed color round trip')
        # Validation must happen before corrupt storage can alter normals.
        before = session.current().normals
        cmds.setAttr(shape+'.abnormalNormals', '{}', type='string')
        expect_error(session.load_vectors, 'does not match')
        vectors(session.current().normals, before, 'invalid storage changed normals')

    @case('Rename, deletion, instance and topology guards')
    def guards():
        cube, shape, session, mesh = fixture()
        cube = cmds.rename(cube, 'abnormalRenamed_'+suffix)
        check(session.current().signature == mesh.signature, 'Rename invalidated session')
        instance = cmds.instance(cube)[0]
        try:
            expect_error(session.current)
        finally:
            cmds.delete(instance)
        cmds.polyTriangulate(session.shape, constructionHistory=False)
        expect_error(session.current, 'topology')
        _, shape, deleted, _ = fixture()
        cmds.delete(cmds.listRelatives(shape, parent=True, fullPath=True)[0])
        expect_error(deleted.current, 'removed')

    def new_panel():
        if cmds.about(batch=True):
            raise Skip('Requires interactive Maya/Qt')
        from abnormal_maya import ui
        control = 'AbnormalValidationPanel_'+suffix+str(len(owned_panels))
        panel = ui.Panel()
        panel.setObjectName(control)
        owned_panels.append((panel, control+'WorkspaceControl'))
        panel.show(dockable=True)
        ui.QtWidgets.QApplication.processEvents()
        check(panel.isVisible(), 'Dock panel is not visible')
        check(cmds.workspaceControl(control+'WorkspaceControl', exists=True), 'Workspace control missing')
        return panel

    @case('Qt dock creation, close and fresh reopen')
    def docking():
        if cmds.about(batch=True):
            raise Skip('Requires interactive Maya/Qt')
        from abnormal_maya import ui
        panel = new_panel()
        panel.close()
        ui.QtWidgets.QApplication.processEvents()
        reopened = new_panel()
        check(reopened.isVisible(), 'Reopened panel is hidden')

    @case('Panel selection, set mask, targets, display and finish/cancel')
    def panel_controls():
        _, shape, _, mesh = fixture()
        panel = new_panel()
        panel.start()
        panel.individual.setChecked(True)
        panel.select_all()
        check(len(scene.selected_corners(shape, mesh)) == len(mesh.normals), 'Select all missed corners')
        selected(shape, mesh, [0])
        panel.invert()
        check(scene.selected_corners(shape, mesh) == set(range(len(mesh.normals)))-{0}, 'Invert mismatch')
        selected(shape, mesh, [0])
        # Vertex membership is a supported native Maya component-set type.
        # Some Maya versions broaden stored vertex-face components to vertices.
        membership = cmds.sets([shape+'.vtx[0]'], name='abnormalMask_'+suffix)
        owned_sets.append(membership)
        panel.set_name.setText(membership)
        panel.set_mask()
        expected_mask = {i:1.0 for i in mesh.vertex_corners[0]}
        check(panel.session.weights == expected_mask,
              'Component set mask mismatch: stored members {}; expected {}; got {}'.format(
                  cmds.sets(membership,query=True), expected_mask, panel.session.weights))
        explicit = scene.selected_corners(shape,mesh,items=[scene.component(shape,mesh,0)])
        check(explicit == {0}, 'Explicit face-corner selection was broadened')
        empty_set = cmds.sets(empty=True,name='abnormalEmptyMask_'+suffix)
        owned_sets.append(empty_set)
        panel.set_name.setText(empty_set)
        panel.set_mask()
        check(panel.session.weights == {}, 'Empty component set must protect every corner')
        panel.clear_mask()
        panel.center_target()
        check(all(math.isfinite(w.value()) for w in panel.target), 'Target center is invalid')
        locator = cmds.spaceLocator(name='abnormalTarget_'+suffix)[0]
        locator = cmds.parent(locator, root)[0]
        cmds.setAttr(locator+'.translate', 2,3,4, type='double3')
        cmds.select(locator, replace=True)
        panel.pick_target()
        vectors([tuple(w.value() for w in panel.target)], [(2,3,4)], 'target sampling')
        selected(shape, mesh, [0])
        panel.display.setChecked(True)
        panel.draw_normals()
        display = cmds.polyOptions(shape, query=True, displayNormal=True)
        display = display[0] if isinstance(display, (list, tuple)) else display
        check(bool(display), 'Normal display not enabled')
        panel.display.setChecked(False)
        panel.draw_normals()
        panel.edit('flip')
        panel.cancel()
        vectors(scene.capture(shape).normals, mesh.normals, 'panel cancel')
        panel.start()
        panel.finish()
        check(panel.session.closed, 'Finish left session open')

    @case('Session normal visibility, hidden edit protection and visibility history')
    def visibility():
        _, shape, session, mesh = fixture()
        session.hide(True)
        check(session.visibility.hidden == {0}, 'Hide selected corner mismatch')
        expect_error(session.select, 'No visible selected normals')
        selected(shape,mesh,[0,1])
        session.apply('flip')
        expected = list(mesh.normals)
        expected[1] = core.mul(expected[1],-1)
        vectors(session.current().normals,expected,'hidden corner must not change')
        session.visibility.reveal()
        check(not session.visibility.hidden,'Reveal did not clear hidden corners')
        session.visibility.undo()
        check(session.visibility.hidden == {0},'Visibility undo mismatch')
        session.visibility.redo()
        check(not session.visibility.hidden,'Visibility redo mismatch')
        selected(shape,mesh,[1])
        session.hide(True,unselected=True)
        check(session.visibility.hidden == set(range(len(mesh.normals)))-{1},'Hide unselected mismatch')

    @case('Viewport 2.0 plugin, display payload, rename and cleanup')
    def viewport_overlay():
        if cmds.about(batch=True):
            raise Skip('Requires interactive Maya Viewport 2.0')
        cube, shape, session, mesh = fixture()
        original_selection = cmds.ls(selection=True,long=True,flatten=True) or []
        original_corners = scene.selected_corners(shape,mesh,allow_empty=True)
        original_undo = cmds.undoInfo(query=True,state=True)
        before_keys = set(overlay.PAYLOADS)
        controller = overlay.Controller(session)
        key = controller.key
        try:
            # Adding a second shape can change Maya's textual transform/shape
            # alias while leaving the same corner selected. Compare identity.
            check(scene.selected_corners(shape,mesh,allow_empty=True) == original_corners,
                  'Overlay creation changed corner selection: before {}; after {}'.format(
                      original_selection,cmds.ls(selection=True,long=True,flatten=True)))
            check(cmds.undoInfo(query=True,state=True)==original_undo,'Overlay changed undo enabled state')
            controller.update(wedges=True,size=.4)
            status = controller.check_render()
            check(status.get('successes',0)>0,
                  'No completed VP2 draw callback observed; expose a model viewport and rerun')
            payload = overlay.PAYLOADS[key]
            line_count = sum(len(vertices)//2 for kind,color,vertices in payload[0] if kind=='lines')
            check(line_count==len(mesh.normals),'Overlay collapsed or lost face-corner normals')
            node_selection = om.MSelectionList()
            node_selection.add(controller.node)
            writable = om.MFnDependencyNode(node_selection.getDependNode(0)).canBeWritten
            check(not (writable() if callable(writable) else writable),'Overlay helper must not serialize')
            session.weights={0:1.0}
            controller.update(wedges=True,draw_weights=True,xray=True)
            check(overlay.PAYLOADS[key][1], 'X-ray flag not forwarded')
            check(any(color==(1,0,0,1) for kind,color,vertices in overlay.PAYLOADS[key][0]),
                  'Filter-weight colors missing')
            session.visibility.hide({0})
            controller.update()
            check(sum(len(vertices)//2 for kind,color,vertices in overlay.PAYLOADS[key][0] if kind=='lines') == len(mesh.normals)-1,
                  'Hidden normal still drawn')
            cube=cmds.rename(cube,'abnormalOverlayRenamed_'+suffix)
            controller.update()
            check(cmds.objExists(controller.node),'Rename lost the overlay helper')
            node=controller.node
        finally:
            controller.close()
        check(not cmds.objExists(node),'Overlay cleanup left a helper shape')
        check(set(overlay.PAYLOADS)==before_keys,'Overlay cleanup leaked display payload')
        check(cmds.undoInfo(query=True,state=True)==original_undo,'Overlay cleanup changed undo enabled state')

    @case('Panel custom overlay toggles, hiding and lifecycle cleanup')
    def overlay_panel():
        _, shape, _, mesh=fixture()
        panel=new_panel()
        panel.start()
        panel.individual.setChecked(True)
        panel.overlay_enabled.setChecked(True)
        check(panel.overlay_controller is not None,'Panel could not start the custom overlay')
        key=panel.overlay_controller.key
        node=panel.overlay_controller.node
        panel.overlay_wedges.setChecked(True)
        panel.overlay_weights.setChecked(True)
        panel.overlay_selected_only.setChecked(True)
        panel.overlay_xray.setChecked(True)
        panel.refresh_overlay()
        check(key in overlay.PAYLOADS,'Panel did not publish overlay geometry')
        status = panel.overlay_controller.check_render()
        check(status.get('successes',0)>0,'Panel overlay did not complete a VP2 draw callback')
        panel.hide_normals()
        check(panel.session.visibility.hidden=={0},'Panel hide mismatch')
        panel.reveal_normals()
        check(not panel.session.visibility.hidden,'Panel reveal mismatch')
        panel.finish()
        check(panel.overlay_controller is None and not panel.overlay_timer.isActive(),
              'Finish left a display controller/timer running')
        check(not cmds.objExists(node) and key not in overlay.PAYLOADS,'Finish leaked overlay helper data')

    @case('Bulk normal capture order and grouped native assignment undo')
    def grouped_writes():
        _,shape,session,mesh=fixture()
        fn=om.MFnMesh(scene.mesh_path(shape))
        reference=[scene._triple(fn.getFaceVertexNormal(f,v,om.MSpace.kObject))
                   for f,vertices in enumerate(mesh.faces) for v in vertices]
        vectors(mesh.normals,reference,'bulk normal ID ordering')
        cmds.select(shape,replace=True)
        native=cmds.polyNormalPerVertex
        with mock.patch.object(cmds,'polyNormalPerVertex',wraps=native) as calls:
            session.apply('align',axis=(1,2,3))
        check(calls.call_count==1,'Constant-vector alignment should use one native assignment, got '+str(calls.call_count))
        expected=[core.unit((1,2,3))]*len(mesh.normals)
        vectors(session.current().normals,expected,'grouped align')
        cmds.undo()
        vectors(session.current().normals,mesh.normals,'grouped align undo')

    @case('Unified session history: selection, active, masks, visibility and normals')
    def session_history():
        _,shape,session,mesh=fixture()
        session.set_selection({0,1},active=0)
        session.weights={0:1.0};session.record()
        initial=session.snapshot()
        session.apply('flip')
        changed=session.snapshot()
        session.history_step(-1)
        check(session.snapshot()==initial,'Session undo did not restore the complete state')
        session.history_step(1)
        check(session.snapshot()==changed,'Session redo did not restore the complete state')
        session.hide(True)
        hidden=session.snapshot()
        session.history_step(-1)
        check(session.snapshot()==changed,'Session hide undo mismatch')
        session.history_step(1)
        check(session.snapshot()==hidden,'Session hide redo mismatch')
        session.visibility.reveal();session.weights=None
        session.set_selection({0,1},active=0)
        session.copy_active(True)
        result=session.current()
        vectors([result.normals[1]],[result.normals[0]],'active to selection')

    @case('Native edge shading parity, native/session undo and exact restoration')
    def shading_state():
        cube,shape,session,mesh=fixture()
        original_fn=om.MFnMesh(scene.mesh_path(shape))
        original_flags=tuple(original_fn.isEdgeSmooth(i) for i in range(original_fn.numEdges))
        _,original_ids=original_fn.getNormalIds()
        original_locks=tuple(original_fn.isNormalLocked(i) for i in original_ids)

        # Compare against *native Maya* on a duplicate instead of asserting the
        # impossible combination of all-soft cube edges and split hard normals.
        reference=cmds.duplicate(cube,name='abnormalShadeReference_'+suffix)[0]
        reference_shape=scene.mesh_path(reference).fullPathName()
        reference_edges=[reference_shape+'.e[{}]'.format(i)
                         for i in range(original_fn.numEdges)]
        cmds.polySoftEdge(reference_edges,angle=180,constructionHistory=False)
        expected_soft=scene.capture(reference_shape).normals
        ref_fn=om.MFnMesh(scene.mesh_path(reference_shape))
        _,ref_ids=ref_fn.getNormalIds()
        expected_soft_locks=tuple(ref_fn.isNormalLocked(i) for i in ref_ids)
        selected(shape,mesh,[0])

        session.shading(True)
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(all(fn.isEdgeSmooth(i) for i in range(fn.numEdges)),
              'Smooth edge flags missing')
        vectors(session.current().normals,expected_soft,'Soft shading differs from native Maya')
        _,ids=fn.getNormalIds()
        soft_locks=tuple(fn.isNormalLocked(i) for i in ids)
        check(soft_locks==expected_soft_locks,'Soft shading locks differ from native Maya')

        # Maya's own Undo/Redo must round-trip the entire shading operation.
        cmds.undo()
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(tuple(fn.isEdgeSmooth(i) for i in range(fn.numEdges))==original_flags,
              'Native undo did not restore original edge flags')
        vectors(session.current().normals,mesh.normals,'Native shading undo')
        _,ids=fn.getNormalIds()
        check(tuple(fn.isNormalLocked(i) for i in ids)==original_locks,
              'Native undo did not restore original normal locks')
        cmds.redo()
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(all(fn.isEdgeSmooth(i) for i in range(fn.numEdges)),
              'Native redo lost smooth edge flags')
        vectors(session.current().normals,expected_soft,'Native shading redo')
        _,ids=fn.getNormalIds()
        check(tuple(fn.isNormalLocked(i) for i in ids)==soft_locks,
              'Native redo lost smooth normal locks')

        # Editor history is intentionally independent of Maya's native undo.
        # Native undo/redo can change selection (or round-trip floating-point
        # normals with tiny differences). History.move() snapshots that
        # *external* state as its own entry before undoing an editor action.
        recorded_state=session.history.states[session.history.position]
        actual_state=session.snapshot()
        if actual_state!=recorded_state:
            changed={key for key in recorded_state
                     if actual_state[key]!=recorded_state[key]}
            print('Maya-native undo/redo produced unrecorded session fields:',
                  ', '.join(sorted(changed)))
            check(changed<={'selected','active','normals'},
                  'Native undo/redo unexpectedly changed saved scene data: '+str(changed))
            if 'normals' in changed:
                vectors(actual_state['normals'],recorded_state['normals'],
                        'Native redo unexpectedly changed normals')
            # The first session undo captures the external state and returns
            # to the recorded post-shading snapshot (still smooth). The next
            # undo is the actual shading operation. Do not mislabel the first
            # undo as a failure to restore the previous edge flags.
            session.history_step(-1)
            check(session.snapshot()==recorded_state,
                  'First session undo did not recover pre-native-history snapshot')
        session.history_step(-1)
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(tuple(fn.isEdgeSmooth(i) for i in range(fn.numEdges))==original_flags,
              'Session undo did not restore original edge flags')
        vectors(session.current().normals,mesh.normals,'Session shading undo')
        _,ids=fn.getNormalIds()
        check(tuple(fn.isNormalLocked(i) for i in ids)==original_locks,
              'Session undo did not restore original locks')
        session.history_step(1)
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(all(fn.isEdgeSmooth(i) for i in range(fn.numEdges)),
              'Session redo did not restore smooth flags')
        vectors(session.current().normals,expected_soft,'Session shading redo')
        _,ids=fn.getNormalIds()
        check(tuple(fn.isNormalLocked(i) for i in ids)==soft_locks,
              'Session redo did not restore smooth normal locks')

        # For hardening, use the identical native Maya reference as an oracle.
        cmds.polySoftEdge(reference_edges,angle=0,constructionHistory=False)
        expected_hard=scene.capture(reference_shape).normals
        session.shading(False)
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(not any(fn.isEdgeSmooth(i) for i in range(fn.numEdges)),
              'Hard edge flags missing')
        vectors(session.current().normals,expected_hard,'Hard shading differs from native Maya')

        session.restore()
        check(session.closed, 'Cancel should close the editing session')
        # Session.current() must reject access after restore() closes it.
        # Inspect the underlying mesh directly for post-cancel assertions.
        fn=om.MFnMesh(scene.mesh_path(shape))
        check(tuple(fn.isEdgeSmooth(i) for i in range(fn.numEdges))==original_flags,
              'Cancel did not restore edge flags')
        vectors(scene.capture(shape).normals,mesh.normals,'Cancel did not restore original normals')
        _,ids=fn.getNormalIds()
        check(tuple(fn.isNormalLocked(i) for i in ids)==original_locks,
              'Cancel did not restore original normal locks')

    @case('Direct projection, occlusion and topology selection adapters')
    def picking_adapters():
        if cmds.about(batch=True): raise Skip('Requires a viewport camera')
        from abnormal_maya import picking,selection
        _,shape,session,mesh=fixture()
        from maya.api import OpenMayaUI as omui
        view=omui.M3dView.active3dView();original_camera=view.getCamera()
        camera=cmds.camera(name='abnormalProjectionCamera_'+suffix)[0]
        camera=cmds.parent(camera,root)[0]
        cmds.setAttr(camera+'.translateZ',5)
        camera_shape=cmds.listRelatives(camera,shapes=True,fullPath=True)[0]
        camera_selection=om.MSelectionList();camera_selection.add(camera_shape)
        try:
            view.setCamera(camera_selection.getDagPath(0));cmds.refresh(force=True)
            all_markers=picking.project(session,xray=True,view=view)
            visible=picking.project(session,xray=False,view=view)
            check(bool(all_markers),'No projected corners in the controlled test camera')
            check(set(visible)<=set(all_markers),'Occlusion added invisible candidates')
            check(0<len(visible)<len(all_markers),'Occlusion did not distinguish front and back cube corners')
            for index in all_markers:
                check(len(all_markers[index][2])==3,'Corner wedge projection is not triangular')
        finally:
            view.setCamera(original_camera)
        session.set_selection({0})
        picking.topology_selection(session,'linked',True)
        check(scene.selected_corners(shape,mesh)==set(range(len(mesh.normals))),'Linked selection missed connected cube corners')
        cmds.select([shape+'.vtx[0]',shape+'.vtx[6]'],replace=True)
        picking.topology_selection(session,'vertex_path',False)
        chosen=scene.selected_corners(shape,mesh)
        graph=selection.Topology(mesh)
        path=graph.path(0,6)
        check(chosen=={i for v in path for i in mesh.vertex_corners[v]},'Vertex path adapter mismatch')

    @case('Picker installation, scoped key events and teardown')
    def picker_lifecycle():
        _,shape,session,mesh=fixture()
        panel=new_panel();panel.start();panel.individual.setChecked(True)
        panel.pick_tool()
        try:
            check(tools._INTERACTION is not None,'Picker filter was not installed')
            from abnormal_maya import ui
            event=ui.QtGui.QKeyEvent(ui.QtCore.QEvent.KeyPress,ui.QtCore.Qt.Key_B,ui.QtCore.Qt.NoModifier)
            check(tools._INTERACTION.event(event),'Picker did not handle its scoped B shortcut')
            check(panel.selection_mode.currentText()=='Box','Picker shortcut did not switch selection mode')
            panel.shortcuts_enabled.setChecked(False)
            check(not tools._INTERACTION.event(event),'Disabled shortcuts still captured B')
        finally: tools.stop()
        check(tools._INTERACTION is None,'Picker teardown retained an event filter')

    @case('Preferences round trip, native Qt binding and shortcut scope')
    def saved_preferences():
        from abnormal_maya import preferences,ui
        existed=cmds.optionVar(exists=preferences.KEY)
        old=cmds.optionVar(query=preferences.KEY) if existed else None
        try:
            panel=new_panel()
            panel.selection_mode.setCurrentText('Lasso')
            panel.selection_radius.setValue(37)
            panel.save_preferences()
            values=preferences.load()
            check(values['selection_mode']=='Lasso' and values['selection_radius']==37,'Saved preferences mismatch')
            check(ui.QtCore.qVersion().split('.')[0]==str(cmds.about(qtVersion=True)).split('.')[0],
                  'Qt binding differs from the Maya host')
            check(all(s.context()==ui.QtCore.Qt.WidgetWithChildrenShortcut for s in panel.scoped_shortcuts),
                  'A shortcut escaped the panel scope')
            panel.shortcuts_enabled.setChecked(False)
            check(all(not s.isEnabled() for s in panel.scoped_shortcuts),'Shortcut disable failed')
        finally:
            if existed: cmds.optionVar(stringValue=(preferences.KEY,old))
            elif cmds.optionVar(exists=preferences.KEY): cmds.optionVar(remove=preferences.KEY)

    @case('Live point/sphere targets: preview, cancel, confirm and helper cleanup')
    def live_targets():
        if cmds.about(batch=True): raise Skip('Requires native manipulators')
        for mode in ('point','sphere'):
            _,shape,session,mesh=fixture()
            panel=new_panel();panel.start();panel.individual.setChecked(True)
            panel.space.setCurrentText('Object');panel.strength.setValue(1)
            for w,v in zip(panel.target,(2,3,4)): w.setValue(v)
            before=panel.require().snapshot()
            live=tools.manipulate(panel,mode)
            try:
                check(live.error is None,'Live initialization failed: '+str(live.error))
                fn=om.MFnTransform(live.path)
                fn.setTranslation(om.MVector(3,4,5),om.MSpace.kWorld)
                live.tick()
                check(live.error is None,'Live preview failed: '+str(live.error))
                expected=core.edit(mesh,{0},mode,target=(3,4,5),strength=1)
                vectors(panel.require().current().normals,expected,mode+' live preview')
                driver=live.driver
                tools.finish_manipulation(False)
                check(not cmds.objExists(driver),'Cancel leaked live target')
                check(panel.require().snapshot()==before,'Cancel did not restore full state')
                live=tools.manipulate(panel,mode);driver=live.driver
                fn=om.MFnTransform(live.path);fn.setTranslation(om.MVector(5,4,3),om.MSpace.kWorld);live.tick()
                tools.finish_manipulation(True)
                expected=core.edit(mesh,{0},mode,target=(5,4,3),strength=1)
                vectors(panel.require().current().normals,expected,mode+' confirm')
                check(not cmds.objExists(driver),'Confirm leaked live target')
            finally: tools.stop()

    @case('Native rotation rings: quaternion preview and full-state cancel')
    def rotation_rings():
        if cmds.about(batch=True): raise Skip('Requires native manipulators')
        _,shape,session,mesh=fixture()
        panel=new_panel();panel.start();panel.individual.setChecked(True);panel.space.setCurrentText('World')
        before=panel.require().snapshot()
        live=tools.manipulate(panel,'rotate')
        try:
            quaternion=om.MQuaternion(math.radians(30),om.MVector(1,0,0))
            om.MFnTransform(live.path).setRotation(quaternion,om.MSpace.kTransform)
            live.tick()
            check(live.error is None,'Rotation-ring preview failed: '+str(live.error))
            expected=core.edit(mesh,{0},'rotate',axis=(1,0,0),angle=math.radians(30))
            vectors(panel.require().current().normals,expected,'Native ring preview')
            tools.finish_manipulation(False)
            check(panel.require().snapshot()==before,'Ring cancel did not restore state')
        finally: tools.stop()

    @case('Editable construction history and blendShape representative workflow')
    def history_deformer():
        cube=cmds.polyCube(name='abnormalHistory_'+suffix,constructionHistory=True)[0]
        cube=cmds.parent(cube,root)[0]
        target=cmds.duplicate(cube,name='abnormalBlendTarget_'+suffix)[0]
        cmds.move(.2,0,0,target+'.vtx[0]',relative=True,objectSpace=True)
        blend=cmds.blendShape(target,cube,name='abnormalBlend_'+suffix,frontOfChain=True)[0]
        owned_sets.append(blend)
        cmds.setAttr(blend+'.weight[0]',.5)
        shape=scene.mesh_path(cube).fullPathName()
        cmds.select(shape,replace=True)
        session=scene.Session(shape);mesh=session.current();selected(shape,mesh,[0])
        session.apply('flip')
        expected=list(mesh.normals);expected[0]=core.mul(expected[0],-1)
        vectors(session.current().normals,expected,'BlendShape normal edit')
        vectors(session.current().points,mesh.points,'Normal edit moved deformed vertices')
        check(abs(cmds.getAttr(blend+'.weight[0]')-.5)<1e-8,'Normal edit changed blendShape weight')
        cmds.undo();vectors(session.current().normals,mesh.normals,'BlendShape normal undo')

    @case('Representative 10,000-corner mesh: capture, grouped edit and overlay timing')
    def larger_mesh():
        plane=cmds.polyPlane(name='abnormalProfile_'+suffix,subdivisionsX=50,subdivisionsY=50,
                            width=10,height=10,constructionHistory=False)[0]
        plane=cmds.parent(plane,root)[0]
        shape=scene.mesh_path(plane).fullPathName();cmds.select(shape,replace=True)
        start=time.perf_counter();session=scene.Session(shape);capture_seconds=time.perf_counter()-start
        original=session.current()
        start=time.perf_counter();session.apply('align',axis=(1,2,3));edit_seconds=time.perf_counter()-start
        vectors(session.current().normals,[core.unit((1,2,3))]*len(original.normals),'larger-mesh grouped normals')
        overlay_seconds=None
        if not cmds.about(batch=True):
            controller=overlay.Controller(session)
            try:
                start=time.perf_counter();controller.update(wedges=True);overlay_seconds=time.perf_counter()-start
                controller.check_render()
            finally: controller.close()
        metrics=dict(vertices=len(original.points),corners=len(original.normals),
                     session_capture_seconds=capture_seconds,grouped_edit_seconds=edit_seconds,
                     overlay_seconds=overlay_seconds)
        print('MAYA PROFILE: '+json.dumps(metrics))
        return metrics

    @case('Native rotate-context creation and callback math (synthetic pointer input)')
    def rotation_callbacks():
        if cmds.about(batch=True):
            raise Skip('Requires a Maya viewport')
        _, shape, session, mesh = fixture()
        tools.rotate(session, axis=(1,0,0))
        check(cmds.currentCtx() == tools._CONTEXT, 'Rotation context was not activated')
        native_query = cmds.draggerContext
        def query(*args, **kwargs):
            if kwargs.get('query') and kwargs.get('anchorPoint'):
                return (0,0,0)
            if kwargs.get('query') and kwargs.get('dragPoint'):
                return (40,0,0)
            return native_query(*args, **kwargs)
        # Only pointer coordinates are simulated. Maya scene edits are real.
        with mock.patch.object(cmds, 'draggerContext', side_effect=query):
            tools._TOOL.press()
            check(tools._TOOL.baseline is not None, 'Press callback failed')
            tools._TOOL.drag()
            expected = core.edit(mesh, {0}, 'rotate', axis=(1,0,0), angle=math.radians(20))
            vectors(session.current().normals, expected, 'drag callback')
            tools._TOOL.drag()
            vectors(session.current().normals, expected, 'drag must not compound')
            tools._TOOL.release()
            check(tools._TOOL.baseline is None, 'Release did not clear gesture state')
        tools.stop()
        check(cmds.currentCtx() != tools._CONTEXT, 'Rotation context did not exit')

    try:
        print('\nAbnormal Maya extended validation — Maya {}, package {}'.format(cmds.about(version=True), abnormal_maya.__version__))
        print('Adapter:', scene.__file__)
        print('Native command tests add undo-history entries; the scene is never reset or saved.')
        for name, callback in cases:
            started=time.perf_counter()
            try:
                metrics=callback()
                item = dict(name=name, status='PASS')
                if isinstance(metrics,dict): item['metrics']=metrics
            except Skip as exc:
                item = dict(name=name, status='SKIP', detail=str(exc))
            except Exception as exc:
                item = dict(name=name, status='FAIL', detail=str(exc), traceback=traceback.format_exc())
            item['seconds']=round(time.perf_counter()-started,4)
            results.append(item)
            print('{}: {}{}'.format(item['status'], name, '\n'+item['detail'] if 'detail' in item else ''))
            if item['status'] == 'FAIL':
                print(item['traceback'])
    finally:
        tools.stop()
        if not preexisting_context:
            tools.stop()
            if cmds.draggerContext(tools._CONTEXT, exists=True):
                cmds.deleteUI(tools._CONTEXT)
        for panel, control in owned_panels:
            try:
                panel.close()
            except RuntimeError:
                pass
            if cmds.workspaceControl(control, exists=True):
                cmds.deleteUI(control)
        for node in owned_sets+[root]:
            if cmds.objExists(node):
                cmds.delete(node)
        tools._CONTEXT = previous_context_name
        tools._TOOL = previous_tool_object
        cmds.softSelect(softSelectEnabled=soft_enabled, softSelectDistance=soft_distance,
                        softSelectFalloff=soft_falloff)
        surviving = [item for item in previous_selection if cmds.objExists(item)]
        cmds.select(surviving, replace=True) if surviving else cmds.select(clear=True)
        try:
            cmds.setToolTo(previous_tool)
        except RuntimeError:
            pass
    manual_checks = ['Actual mouse press/drag/release rotates the selected normal',
                     'One native Undo reverses one complete mouse gesture; Redo restores it',
                     'Dock/undock and normal-line appearance are usable at your display scale',
                     'Custom VP2 overlay shows selection colors, wedges and positive mask-weight colors',
                     'Custom overlay X-ray and selected-only toggles visibly change the display',
                     'Hide/reveal and visibility undo/redo affect normals without hiding mesh geometry',
                     'Picker click/box/circle/lasso and Shift/Ctrl modifiers select the intended corners on a HiDPI viewport',
                     'Picker X-ray selects back-side corners; occlusion mode excludes them; Alt navigation remains native',
                     'Native rotation rings preview normals; Confirm keeps them and Cancel restores the original state',
                     'Live point/sphere targets follow native movement; Enter confirms and Escape cancels',
                     'Session history restores normals, selection, active corner, weights and hidden state together',
                     'Saved preferences reopen correctly; scoped shortcuts do not affect other Maya panels']
    report = dict(maya=cmds.about(version=True),python=sys.version,qt=cmds.about(qtVersion=True), package=abnormal_maya.__version__,
                  adapter=scene.__file__, automated=results,
                  manual=[dict(name=name, status='PENDING') for name in manual_checks])
    print('\nAUTOMATED: {} passed, {} failed, {} skipped.'.format(
        sum(r['status']=='PASS' for r in results), sum(r['status']=='FAIL' for r in results),
        sum(r['status']=='SKIP' for r in results)))
    for name in manual_checks:
        print('PENDING MANUAL: '+name)
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Report:', report_path)
    if manual and not cmds.about(batch=True):
        _show_manual(report)
    if any(r['status']=='FAIL' for r in results):
        raise RuntimeError('Abnormal extended validation failed; copy the FAIL details printed above')
    return report


_MANUAL = None


def _show_manual(report):
    """Modeless checklist: users can manipulate Maya while it stays open."""
    global _MANUAL
    from maya import cmds
    from abnormal_maya import ui, scene, tools
    QtWidgets = ui.QtWidgets
    if _MANUAL is not None:
        try:
            _MANUAL.raise_()
            return
        except RuntimeError:
            pass

    class Checklist(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Abnormal Maya — remaining viewport checks')
            self.setMinimumWidth(480)
            self.root = None
            self.panel = None
            self.control = None
            self.saved_selection = cmds.ls(selection=True, long=True) or []
            self.saved_tool = cmds.currentCtx()
            layout = QtWidgets.QVBoxLayout(self)
            text = QtWidgets.QLabel('Click Prepare, select the test corner, then use Drag to rotate.\n'
                'Drag in the viewport; use Undo/Redo. Dock/undock the test panel.\n'
                'Try the custom overlay toggles, masks, and Hide/Reveal controls.\n'
                'Mark each result below. Close this window to remove the test cube.\n'
                'Your scene is not reset or saved; test commands remain in undo history.')
            text.setWordWrap(True)
            layout.addWidget(text)
            button = QtWidgets.QPushButton('Prepare test cube and panel')
            button.clicked.connect(self.prepare)
            layout.addWidget(button)
            scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True)
            choices=QtWidgets.QWidget();choices_layout=QtWidgets.QVBoxLayout(choices)
            scroll.setWidget(choices);layout.addWidget(scroll)
            self.resize(600,700)
            for item in report['manual']:
                row = QtWidgets.QHBoxLayout()
                label = QtWidgets.QLabel(item['name'])
                label.setWordWrap(True)
                row.addWidget(label)
                choice = QtWidgets.QComboBox()
                choice.addItems(['PENDING', 'PASS', 'FAIL'])
                choice.currentTextChanged.connect(lambda value, item=item: self.record(item,value))
                row.addWidget(choice)
                choices_layout.addLayout(row)
            button = QtWidgets.QPushButton('Print complete report')
            button.clicked.connect(lambda: print(json.dumps(report,indent=2)))
            layout.addWidget(button)

        def record(self, item, value):
            item['status'] = value
            print('MANUAL {}: {}'.format(value,item['name']))

        def prepare(self):
            if self.root:
                return
            try:
                self.root = cmds.polyCube(name='abnormalManualCheck#', constructionHistory=False)[0]
                shape = scene.mesh_path(self.root).fullPathName()
                mesh = scene.capture(shape)
                cmds.select(scene.component(shape,mesh,0), replace=True)
                self.panel = ui.Panel()
                name = 'AbnormalManualPanel_'+uuid.uuid4().hex[:8]
                self.panel.setObjectName(name)
                self.control = name+'WorkspaceControl'
                self.panel.show(dockable=True)
                self.panel.individual.setChecked(True)
                self.panel.start()
                self.panel.overlay_enabled.setChecked(True)
                self.panel.overlay_wedges.setChecked(True)
                self.panel.refresh_overlay()
                # Enable explicit, observable rotation around X for the test.
                self.panel.axis.setCurrentIndex(0)
                print('Manual test cube:', self.root)
            except Exception:
                traceback.print_exc()

        def closeEvent(self, event):
            global _MANUAL
            if self.panel is not None:
                try:
                    self.panel.close()
                except RuntimeError:
                    pass
            if self.control and cmds.workspaceControl(self.control,exists=True):
                cmds.deleteUI(self.control)
            if self.root and cmds.objExists(self.root):
                cmds.delete(self.root)
            selection = [s for s in self.saved_selection if cmds.objExists(s)]
            cmds.select(selection,replace=True) if selection else cmds.select(clear=True)
            try:
                cmds.setToolTo(self.saved_tool)
            except RuntimeError:
                pass
            _MANUAL = None
            super().closeEvent(event)

    _MANUAL = Checklist()
    _MANUAL.show()


if __name__ == '__main__':
    run()
