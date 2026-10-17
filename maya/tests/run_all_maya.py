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
import uuid
from unittest import mock


def run(manual=True, report_path=None):
    """Return automated results; optionally open the guided viewport checklist.

    report_path is optional: an explicit JSON path to write the automated report.
    No files are written by default. An automated FAIL raises after all cases run.
    """
    from maya import cmds
    from maya.api import OpenMaya as om
    try:
        import abnormal_maya
    except ImportError:
        if '__file__' not in globals():
            raise RuntimeError('Install Abnormal Maya first')
        scripts = Path(__file__).resolve().parents[1] / 'AbnormalMaya' / 'scripts'
        sys.path.insert(0, str(scripts))
        import abnormal_maya
    from abnormal_maya import core, scene, tools
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya undo before running these tests')
    if tools._TOOL is not None and cmds.currentCtx() == tools._CONTEXT:
        raise RuntimeError('Exit the Abnormal rotation tool with Q before running tests')
    previous_selection = cmds.ls(selection=True, long=True) or []
    previous_tool = cmds.currentCtx()
    soft_enabled = cmds.softSelect(query=True, softSelectEnabled=True)
    soft_distance = cmds.softSelect(query=True, softSelectDistance=True)
    soft_falloff = cmds.softSelect(query=True, softSelectFalloff=True)
    previous_tool_object = tools._TOOL
    preexisting_context = cmds.draggerContext(tools._CONTEXT, exists=True)
    context_available = not preexisting_context
    suffix = uuid.uuid4().hex[:10]
    root = cmds.group(empty=True, name='abnormalValidation_' + suffix)
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
        cmds.setAttr(cube+'.scaleX', 0)
        expect_error(lambda: session.apply('align', space='World'), 'singular')

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
        membership = cmds.sets([scene.component(shape,mesh,0)], name='abnormalMask_'+suffix)
        owned_sets.append(membership)
        panel.set_name.setText(membership)
        panel.set_mask()
        check(panel.session.weights == {0:1.0}, 'Component set mask mismatch')
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

    @case('Native rotate-context creation and callback math (synthetic pointer input)')
    def rotation_callbacks():
        if cmds.about(batch=True):
            raise Skip('Requires a Maya viewport')
        if not context_available:
            raise Skip('Existing Abnormal context preserved; press Q and restart Maya to test creation')
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
            try:
                callback()
                item = dict(name=name, status='PASS')
            except Skip as exc:
                item = dict(name=name, status='SKIP', detail=str(exc))
            except Exception as exc:
                item = dict(name=name, status='FAIL', detail=str(exc), traceback=traceback.format_exc())
            results.append(item)
            print('{}: {}{}'.format(item['status'], name, '\n'+item['detail'] if 'detail' in item else ''))
            if item['status'] == 'FAIL':
                print(item['traceback'])
    finally:
        if not preexisting_context:
            tools.stop()
            if cmds.draggerContext(tools._CONTEXT, exists=True):
                cmds.deleteUI(tools._CONTEXT)
        tools._TOOL = previous_tool_object
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
                     'Dock/undock and normal-line appearance are usable at your display scale']
    report = dict(maya=cmds.about(version=True), package=abnormal_maya.__version__,
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
                'Mark each result below. Close this window to remove the test cube.\n'
                'Your scene is not reset or saved; test commands remain in undo history.')
            text.setWordWrap(True)
            layout.addWidget(text)
            button = QtWidgets.QPushButton('Prepare test cube and panel')
            button.clicked.connect(self.prepare)
            layout.addWidget(button)
            for item in report['manual']:
                row = QtWidgets.QHBoxLayout()
                label = QtWidgets.QLabel(item['name'])
                label.setWordWrap(True)
                row.addWidget(label)
                choice = QtWidgets.QComboBox()
                choice.addItems(['PENDING', 'PASS', 'FAIL'])
                choice.currentTextChanged.connect(lambda value, item=item: self.record(item,value))
                row.addWidget(choice)
                layout.addLayout(row)
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
                self.panel.display.setChecked(True)
                self.panel.draw_normals()
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
