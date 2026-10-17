"""Live point/sphere targets and native Maya rotation-ring manipulators.

Temporary helpers never serialize. Confirm records one session-history step;
Cancel restores normals, locks, selection, filters and active state. Native
preview writes remain undoable but are not held in a long-lived undo chunk.
"""
import uuid
from maya import cmds
from maya.api import OpenMaya as om
from . import core, scene


class Manipulation:
    is_manipulation=True

    def __init__(self,panel,mode):
        from .ui import QtCore,QtWidgets
        self.panel=panel;self.session=panel.require();self.mode=mode
        mesh,self.selected=self.session.select(panel.individual.isChecked())
        source_path=scene.mesh_path(self.session.shape)
        scene._validate_transform(source_path)
        world=source_path.inclusiveMatrix()
        if core.degenerate_basis([tuple(world[r*4+c] for c in range(3)) for r in range(3)]):
            raise ValueError('Cannot manipulate normals with a singular transform')
        self.session.record();self.before=self.session.snapshot()
        self.source_normals=list(mesh.normals)
        self.previous_tool=cmds.currentCtx();self.driver=None;self.driver_uuid=None;self.context=None
        self.last=None;self.closed=False;self.error=None;self.key_filter=None;self.widget=None
        self.options=dict(individual=panel.individual.isChecked(),space=panel.space.currentText(),
                          auto_mirror=tuple(i for i,w in enumerate(panel.auto) if w.isChecked()),
                          strength=panel.strength.value(),align=panel.align_target.isChecked())
        self.timer=QtCore.QTimer(panel)
        self.timer.timeout.connect(self.tick)
        try:
            with scene.undo_chunk('Abnormal live helper'):
                if mode=='rotate':
                    self.driver=cmds.createNode('transform',name='abnormalRotationPivot#',skipSelect=True)
                else:
                    self.driver=cmds.spaceLocator(name='abnormalLiveTarget#')[0]
                selection=om.MSelectionList();selection.add(self.driver)
                self.path=selection.getDagPath(0)
                self.driver_uuid=cmds.ls(self.driver,uuid=True)[0]
                transform=om.MFnTransform(self.path)
                if mode=='rotate':
                    source_path=scene.mesh_path(self.session.shape)
                    center=core.mean(mesh.points[mesh.corner_vertices[i]] for i in self.selected)
                    center=om.MPoint(*center)*source_path.inclusiveMatrix()
                    transform.setTranslation(om.MVector(center.x,center.y,center.z),om.MSpace.kWorld)
                    if self.options['space']=='Object': basis=source_path.inclusiveMatrix()
                    elif self.options['space']=='View':
                        from maya.api import OpenMayaUI as omui
                        camera_path=omui.M3dView.active3dView().getCamera()
                        scene._validate_transform(camera_path)
                        basis=camera_path.inclusiveMatrix()
                    else: basis=om.MMatrix()
                    transform.setRotation(om.MTransformationMatrix(basis).rotation(asQuaternion=True),om.MSpace.kTransform)
                else:
                    transform.setTranslation(om.MVector(*[w.value() for w in panel.target]),om.MSpace.kWorld)
                    if self.options['space']=='Object': basis=scene.mesh_path(self.session.shape).inclusiveMatrix()
                    elif self.options['space']=='View':
                        from maya.api import OpenMayaUI as omui
                        camera_path=omui.M3dView.active3dView().getCamera()
                        scene._validate_transform(camera_path)
                        basis=camera_path.inclusiveMatrix()
                    else: basis=om.MMatrix()
                    transform.setRotation(om.MTransformationMatrix(basis).rotation(asQuaternion=True),om.MSpace.kTransform)
                om.MFnDependencyNode(self.path.node()).setDoNotWrite(True)
                for child in cmds.listRelatives(self.driver,shapes=True,fullPath=True) or []:
                    selection=om.MSelectionList();selection.add(child)
                    om.MFnDependencyNode(selection.getDependNode(0)).setDoNotWrite(True)
                self.initial=om.MMatrix(self.path.inclusiveMatrix())
                for axis in 'XYZ': cmds.setAttr(self.driver+'.scale'+axis,lock=True)
            self.context='abnormalLiveManip_'+uuid.uuid4().hex[:8]
            if mode=='rotate': cmds.manipRotateContext(self.context,mode=0)
            else: cmds.manipMoveContext(self.context,mode=2 if self.options['space']=='World' else 0)
            cmds.select(self.driver,replace=True);cmds.setToolTo(self.context)
            self.session.preview_selection=set(self.selected)
            from maya.api import OpenMayaUI as omui
            if QtCore.qVersion().startswith('6'):
                from shiboken6 import wrapInstance
            else:
                from shiboken2 import wrapInstance
            self.widget=wrapInstance(int(omui.M3dView.active3dView().widget()),QtWidgets.QWidget)
            owner=self
            class Keys(QtCore.QObject):
                def eventFilter(self,watched,event):
                    if event.type()!=QtCore.QEvent.KeyPress: return False
                    cancel_undo=event.key()==QtCore.Qt.Key_Z and bool(event.modifiers() & QtCore.Qt.ControlModifier)
                    if cancel_undo or event.key() in (QtCore.Qt.Key_Return,QtCore.Qt.Key_Enter,QtCore.Qt.Key_Escape):
                        from . import tools
                        keep=not cancel_undo and event.key()!=QtCore.Qt.Key_Escape
                        owner.panel.run(lambda:tools.finish_manipulation(keep),allow_manipulation=True)
                        return True
                    return False
            self.key_filter=Keys(self.widget)
            self.widget.installEventFilter(self.key_filter)
            self.widget.setFocus()
            self.timer.start(100)
            self.tick()
            if self.error is not None: raise RuntimeError(str(self.error))
        except Exception:
            self.cleanup()
            try: self.session.restore_snapshot(self.before)
            except Exception as restore_error: cmds.warning('Abnormal live tool rollback: '+str(restore_error))
            raise

    def tick(self,force=False):
        if self.closed: return
        try:
            matrix=self.path.inclusiveMatrix()
            signature=tuple(round(value,10) for value in matrix)
            if signature==self.last and not force: return
            self.last=signature
            if self.mode=='rotate':
                source_path=scene.mesh_path(self.session.shape)
                world=source_path.inclusiveMatrix();inverse=world.inverse()
                delta=self.initial.inverse()*matrix
                result=list(self.source_normals)
                for i in self.selected:
                    n=om.MVector(*self.source_normals[i]).transformAsNormal(world)
                    n=n.transformAsNormal(delta).transformAsNormal(inverse).normal()
                    result[i]=(n.x,n.y,n.z)
                result=core.blend(self.source_normals,result,self.selected,self.session.weights)
                mesh=self.session.current()
                for axis in self.options['auto_mirror']:
                    result=core.mirror(result,self.selected,self.session._mirror_map(mesh,axis),axis)
                self.session.write_result(result,record_history=False)
            else:
                point=om.MPoint(0,0,0)*matrix
                self.session.apply(self.mode,target=(point.x,point.y,point.z),baseline=self.source_normals,
                                   selected_override=self.selected,record_history=False,**self.options)
                for widget,value in zip(self.panel.target,(point.x,point.y,point.z)):
                    widget.setValue(value)
            self.panel.refresh_overlay()
        except Exception as exc:
            self.error=exc
            self.timer.stop()
            self.panel.status.setText('Live tool paused: '+str(exc)+' — Cancel or Confirm to exit')
            cmds.warning('Abnormal live manipulation: '+str(exc))

    def finish(self,keep):
        if self.closed: return
        self.timer.stop()
        try:
            if keep:
                self.tick(force=True)
                if self.error is not None:
                    self.session.restore_snapshot(self.before)
                    raise RuntimeError('Live preview failed and was cancelled: '+str(self.error))
                self.session._set_selection(self.before['selected'])
                self.session.active_corner=self.before['active']
                self.session.record()
            else: self.session.restore_snapshot(self.before)
        finally:
            self.cleanup()

    def cleanup(self):
        self.closed=True;self.timer.stop()
        self.session.preview_selection=None
        if self.key_filter is not None:
            try:
                self.widget.removeEventFilter(self.key_filter)
                self.key_filter.deleteLater()
            except RuntimeError: pass
        if self.context and cmds.currentCtx()==self.context:
            cmds.setToolTo('selectSuperContext')
        if self.context and cmds.contextInfo(self.context,exists=True): cmds.deleteUI(self.context)
        if self.driver_uuid:
            nodes=cmds.ls(self.driver_uuid,long=True) or []
            self.driver=nodes[0] if len(nodes)==1 else None
        if self.driver and cmds.objExists(self.driver):
            with scene.undo_chunk('Abnormal live helper cleanup'): cmds.delete(self.driver)
        try: cmds.setToolTo(self.previous_tool)
        except RuntimeError: pass

    def stop(self):
        self.finish(False)
