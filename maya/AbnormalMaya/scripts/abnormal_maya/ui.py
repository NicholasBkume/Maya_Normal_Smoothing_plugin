"""Dockable Qt controls using the Qt binding shipped with Maya."""
import math
from maya import cmds
from maya.api import OpenMaya as om
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore
from . import core, scene, tools, overlay

_PANEL = None


class Panel(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('AbnormalMayaPanel')
        self.setWindowTitle('Abnormal Maya — Normal Editor')
        self.setMinimumWidth(330)
        self.session = None
        self.overlay_controller = None
        self.overlay_timer = QtCore.QTimer(self)
        self.overlay_timer.timeout.connect(self.refresh_overlay)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        outer = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.status = QtWidgets.QLabel('Select one mesh or its components, then Start.')
        self.status.setWordWrap(True)
        self.body_layout.addWidget(self.status)
        self.row([('Start session', self.start), ('Finish', self.finish), ('Cancel session', self.cancel)])
        self.individual = QtWidgets.QCheckBox('Edit individual face-vertex normals')
        self.body_layout.addWidget(self.individual)
        self.body_layout.addWidget(QtWidgets.QLabel('Use Maya component selection: vertex, face, edge, or vertex-face.'))
        self.row([('Select all', self.select_all), ('Invert', self.invert),
                  ('Undo', lambda: self.global_history(False)), ('Redo', lambda: self.global_history(True))])
        self.row([('Hide selected normals', lambda: self.hide_normals(False)),
                  ('Hide unselected normals', lambda: self.hide_normals(True)),
                  ('Reveal normals', self.reveal_normals)])
        self.row([('Visibility undo', lambda: self.visibility_history(False)),
                  ('Visibility redo', lambda: self.visibility_history(True))])
        self.space = QtWidgets.QComboBox()
        self.space.addItems(['Object', 'World', 'View'])
        self.form('Editing space', self.space)
        self.axis = QtWidgets.QComboBox()
        self.axis.addItems(['X', 'Y', 'Z'])
        self.form('Axis', self.axis)
        self.angle = self.number(-360, 360, 5, 2)
        self.form('Rotation degrees', self.angle)
        self.row([('Rotate −', lambda: self.edit('rotate', angle=-math.radians(self.angle.value()))),
                  ('Rotate +', lambda: self.edit('rotate', angle=math.radians(self.angle.value())))])
        self.row([('Drag to rotate in viewport', self.rotate_tool)])
        self.row([('Flatten', lambda: self.edit('flatten')),
                  ('Align +', lambda: self.edit('align')),
                  ('Align −', lambda: self.edit('align', axis=core.mul(self.axis_vector(), -1)))])
        self.row([('Flip', lambda: self.edit('flip')), ('Reset selected', lambda: self.edit('reset'))])
        self.row([('Average per vertex', lambda: self.edit('average_vertex')),
                  ('Average selection', lambda: self.edit('average'))])
        self.strength = self.number(0, 1, 0.25, 3)
        self.strength.setSingleStep(0.05)
        self.form('Smooth / target strength', self.strength)
        self.iterations = QtWidgets.QSpinBox()
        self.iterations.setRange(1, 100)
        self.iterations.setValue(5)
        self.form('Smooth iterations', self.iterations)
        self.row([('Smooth normals', lambda: self.edit('smooth')),
                  ('From selected faces', lambda: self.edit('from_faces'))])
        self.smooth_directions = QtWidgets.QCheckBox('Inside/outside: average face directions per vertex')
        self.smooth_directions.setChecked(True)
        self.body_layout.addWidget(self.smooth_directions)
        self.row([('Outside', lambda: self.edit('outside')), ('Inside', lambda: self.edit('inside'))])
        self.body_layout.addWidget(QtWidgets.QLabel('Symmetry (mesh object axes)'))
        auto_row = QtWidgets.QHBoxLayout()
        auto_row.addWidget(QtWidgets.QLabel('Auto mirror'))
        self.auto = []
        for name in ('X', 'Y', 'Z'):
            check = QtWidgets.QCheckBox(name)
            self.auto.append(check)
            auto_row.addWidget(check)
        self.body_layout.addLayout(auto_row)
        self.tolerance = self.number(0, 1000000, 0, 5)
        self.form('Manual mirror distance (object units; 0 = unlimited)', self.tolerance)
        self.row([('Mirror X', lambda: self.mirror(0)), ('Mirror Y', lambda: self.mirror(1)),
                  ('Mirror Z', lambda: self.mirror(2))])
        self.row([('Store active source', self.store), ('Paste source normals', self.paste)])
        self.body_layout.addWidget(QtWidgets.QLabel('Weights (session-local)'))
        self.row([('Mask from selection', self.mask), ('Mask from soft selection', self.soft_mask),
                  ('Clear mask', self.clear_mask)])
        self.set_name = QtWidgets.QLineEdit()
        self.set_name.setPlaceholderText('Maya component set name')
        self.form('Binary mask set', self.set_name)
        self.row([('Mask from set', self.set_mask)])
        self.body_layout.addWidget(QtWidgets.QLabel('Target position — world centimeters'))
        self.target = [self.number(-1e9, 1e9, 0, 4) for _ in range(3)]
        for label, widget in zip(('X', 'Y', 'Z'), self.target):
            self.form(label, widget)
        self.row([('Target from selection', self.pick_target), ('Target at selected center', self.center_target)])
        self.align_target = QtWidgets.QCheckBox('Point mode: align all vectors from selection center')
        self.body_layout.addWidget(self.align_target)
        self.row([('Point toward target', lambda: self.edit('point')),
                  ('Sphereize from target', lambda: self.edit('sphere'))])
        self.body_layout.addWidget(QtWidgets.QLabel('Object-space normal storage (whole mesh)'))
        self.row([('Store on mesh', lambda: self.require().save_vectors()),
                  ('Load from mesh', lambda: self.require().load_vectors())])
        self.row([('Normals → color set', lambda: self.require().colors(True)),
                  ('Color set → normals', lambda: self.require().colors(False))])
        self.display = QtWidgets.QCheckBox('Show Maya face-vertex normals')
        self.display.toggled.connect(lambda _: self.run(self.draw_normals))
        self.body_layout.addWidget(self.display)
        self.normal_size = self.number(0.001, 10000, 0.4, 3)
        self.form('Normal display size (overlay: world cm)', self.normal_size)
        self.normal_size.valueChanged.connect(lambda _: self.run(self.draw_normals))
        self.overlay_enabled = QtWidgets.QCheckBox('Custom normal overlay (Viewport 2.0)')
        self.overlay_enabled.toggled.connect(lambda _: self.run(self.toggle_overlay))
        self.body_layout.addWidget(self.overlay_enabled)
        self.overlay_selected_only = QtWidgets.QCheckBox('Overlay: show only selected normals')
        self.overlay_scale_selected = QtWidgets.QCheckBox('Overlay: enlarge selected normals')
        self.overlay_scale_selected.setChecked(True)
        self.overlay_weights = QtWidgets.QCheckBox('Overlay: color by filter weights')
        self.overlay_wedges = QtWidgets.QCheckBox('Overlay: draw individual corner wedges')
        self.overlay_xray = QtWidgets.QCheckBox('Overlay: X-ray')
        for check in (self.overlay_selected_only,self.overlay_scale_selected,self.overlay_weights,
                      self.overlay_wedges,self.overlay_xray):
            check.toggled.connect(lambda _: self.refresh_overlay())
            self.body_layout.addWidget(check)
        self.overlay_point_size = self.number(1,20,4,1)
        self.form('Overlay point size (pixels)',self.overlay_point_size)
        self.overlay_point_size.valueChanged.connect(lambda _: self.refresh_overlay())
        self.body_layout.addWidget(QtWidgets.QLabel('Finish keeps edits. Cancel restores session-start normals.\n'
                                              'Closing the panel keeps edits. Undo/Redo use Maya’s global history.'))
        self.body_layout.addStretch()

    def row(self, buttons):
        layout = QtWidgets.QHBoxLayout()
        for label, callback in buttons:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda checked=False, callback=callback: self.run(callback))
            layout.addWidget(button)
        self.body_layout.addLayout(layout)

    def form(self, label, widget):
        layout = QtWidgets.QFormLayout()
        layout.addRow(label, widget)
        self.body_layout.addLayout(layout)

    @staticmethod
    def number(minimum, maximum, default, decimals):
        widget = QtWidgets.QDoubleSpinBox()
        widget.setDecimals(decimals)
        widget.setRange(minimum, maximum)
        widget.setValue(default)
        return widget

    def run(self, callback):
        try:
            callback()
            if self.session and not self.session.closed:
                self.status.setText('Editing ' + self.session.shape + (' — weight mask active' if self.session.weights is not None else ''))
        except Exception as exc:
            self.status.setText(str(exc))
            cmds.warning('Abnormal Maya: ' + str(exc))

    def require(self):
        if not self.session or self.session.closed:
            raise ValueError('Start a session first')
        return self.session

    def start(self):
        if self.session and not self.session.closed:
            raise ValueError('Finish or cancel the current session before starting another')
        self.session = scene.Session()

    def finish(self):
        session = self.require()
        tools.stop()
        self.stop_overlay()
        session.closed = True
        self.status.setText('Finished. Normal edits kept; Maya Undo remains available.')

    def cancel(self):
        tools.stop()
        self.stop_overlay()
        self.require().restore()
        self.status.setText('Session-start normals restored. Maya Undo can undo the restore.')

    def axis_vector(self):
        axis = [0, 0, 0]
        axis[self.axis.currentIndex()] = 1
        return tuple(axis)

    def edit(self, operation, **options):
        defaults = dict(axis=self.axis_vector(), strength=self.strength.value(),
                        iterations=self.iterations.value(), align=self.align_target.isChecked(),
                        smooth_shading=self.smooth_directions.isChecked())
        defaults.update(options)
        if operation in ('point', 'sphere'):
            defaults['target'] = tuple(w.value() for w in self.target)
        self.require().apply(operation, individual=self.individual.isChecked(),
                             space=self.space.currentText(),
                             auto_mirror=[i for i, check in enumerate(self.auto) if check.isChecked()],
                             **defaults)

    def rotate_tool(self):
        tools.rotate(self.require(), axis=self.axis_vector(), space=self.space.currentText(),
                     individual=self.individual.isChecked(),
                     auto_mirror=[i for i, check in enumerate(self.auto) if check.isChecked()])

    def mirror(self, axis):
        self.require().mirror(axis, self.individual.isChecked(), self.tolerance.value() or None)

    def store(self):
        self.require().store(self.individual.isChecked())
        self.status.setText('Source corner references stored. Select destination components and Paste.')

    def paste(self):
        self.require().paste(self.individual.isChecked())

    def mask(self):
        self.require().mask_selection(self.individual.isChecked())

    def soft_mask(self):
        self.require().mask_soft_selection()

    def clear_mask(self):
        self.require().weights = None

    def set_mask(self):
        session = self.require()
        session.mask_set(self.set_name.text().strip(), self.individual.isChecked())

    def pick_target(self):
        items = cmds.ls(selection=True, objectsOnly=True, long=True) or []
        if len(items) != 1:
            raise ValueError('Select one target transform or locator')
        selection = om.MSelectionList()
        selection.add(items[0])
        point = om.MPoint(0, 0, 0) * selection.getDagPath(0).inclusiveMatrix()
        for widget, value in zip(self.target, (point.x, point.y, point.z)):
            widget.setValue(value)

    def center_target(self):
        session = self.require()
        mesh, selected = session.select(self.individual.isChecked())
        p = core.mean(mesh.points[mesh.corner_vertices[i]] for i in selected)
        point = om.MPoint(*p) * scene.mesh_path(session.shape).inclusiveMatrix()
        for widget, value in zip(self.target, (point.x, point.y, point.z)):
            widget.setValue(value)

    def select_all(self):
        session = self.require()
        mesh = session.current()
        cmds.select([scene.component(session.shape, mesh, i) for i in range(len(mesh.normals))
                     if i not in session.visibility.hidden], replace=True)

    def invert(self):
        session = self.require()
        mesh, selected = session.select(self.individual.isChecked())
        cmds.select([scene.component(session.shape, mesh, i) for i in range(len(mesh.normals)) if i not in selected and i not in session.visibility.hidden], replace=True)

    def draw_normals(self):
        shape = self.require().shape
        with scene.undo_chunk('Abnormal normal display'):
            cmds.polyOptions(shape, displayNormal=self.display.isChecked(),
                             sizeNormal=self.normal_size.value(), point=False, facet=False, pointFacet=True)

    def toggle_overlay(self):
        self.stop_overlay(keep_checkbox=True)
        if self.overlay_enabled.isChecked():
            try:
                self.overlay_controller = overlay.Controller(self.require())
                self.refresh_overlay()
                if self.overlay_controller:
                    self.overlay_timer.start(200)
            except Exception:
                self.stop_overlay()
                raise

    def refresh_overlay(self):
        if self.overlay_controller is None:
            return
        try:
            self.overlay_controller.update(
                individual=self.individual.isChecked(),size=self.normal_size.value(),
                selected_only=self.overlay_selected_only.isChecked(),
                scale_selected=self.overlay_scale_selected.isChecked(),
                draw_weights=self.overlay_weights.isChecked(),
                wedges=self.overlay_wedges.isChecked(),xray=self.overlay_xray.isChecked(),
                point_size=self.overlay_point_size.value())
        except Exception as exc:
            self.stop_overlay()
            self.status.setText('Overlay stopped: '+str(exc))
            cmds.warning('Abnormal overlay: '+str(exc))

    def stop_overlay(self, keep_checkbox=False):
        self.overlay_timer.stop()
        if self.overlay_controller is not None:
            self.overlay_controller.close()
            self.overlay_controller = None
        if not keep_checkbox:
            self.overlay_enabled.blockSignals(True)
            self.overlay_enabled.setChecked(False)
            self.overlay_enabled.blockSignals(False)

    def hide_normals(self, unselected=False):
        session = self.require()
        # Native display cannot hide individual corner normals. Use the custom
        # overlay for visibility without hiding any mesh faces/vertices.
        self.display.setChecked(False)
        if not self.overlay_enabled.isChecked():
            self.overlay_enabled.setChecked(True)
        if self.overlay_controller is None:
            raise RuntimeError('Enable the custom overlay before hiding normals')
        session.hide(self.individual.isChecked(),unselected=unselected)
        self.refresh_overlay()

    def reveal_normals(self):
        self.require().visibility.reveal()
        self.refresh_overlay()

    def visibility_history(self, redo=False):
        visibility = self.require().visibility
        visibility.redo() if redo else visibility.undo()
        self.refresh_overlay()

    def global_history(self, redo=False):
        cmds.redo() if redo else cmds.undo()

    def closeEvent(self, event):
        # Closing preserves scene changes. Explicit Cancel restores normals.
        tools.stop()
        self.stop_overlay()
        self.session = None
        super().closeEvent(event)


def show():
    global _PANEL
    if _PANEL is not None:
        try:
            _PANEL.show(dockable=True)
            _PANEL.raise_()
            return _PANEL
        except RuntimeError:
            _PANEL = None
    _PANEL = Panel()
    _PANEL.show(dockable=True)
    return _PANEL
