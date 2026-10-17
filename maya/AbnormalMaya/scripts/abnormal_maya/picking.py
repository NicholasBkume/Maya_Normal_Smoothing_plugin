"""Maya viewport projection, source-mesh occlusion and Qt selection tools."""
import math
from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaUI as omui
from . import core, scene, selection


def project(session, individual=True, size=.4, xray=False, scale_selected=True,selected_only=False,view=None,wedge_scale=.18):
    mesh=session.current()
    path=scene.mesh_path(session.shape)
    scene._validate_transform(path)
    matrix=path.inclusiveMatrix()
    view=view or omui.M3dView.active3dView()
    camera_inverse=view.getCamera().inclusiveMatrixInverse()
    fn=om.MFnMesh(path)
    accelerator=fn.autoUniformGridParams()
    selected=scene.selected_corners(session.shape,mesh,individual,allow_empty=True)
    items=cmds.ls(selection=True,long=True,flatten=True) or []
    if session.active_corner is not None and session.active_corner in selected:
        active={session.active_corner}
    else:
        active=scene.selected_corners(session.shape,mesh,individual,items=items[-1:],allow_empty=True) if items and '.' in items[-1] else set()
    markers={}
    for i,n in enumerate(mesh.normals):
        if i in session.visibility.hidden or (selected_only and i not in selected): continue
        vertex=mesh.corner_vertices[i];face=mesh.corner_faces[i]
        p=om.MPoint(*mesh.points[vertex])*matrix
        if (p*camera_inverse).z>=0: continue
        world_normal=om.MVector(*n).transformAsNormal(matrix).normal()
        factor=(1 if i in active else .666 if i in selected else .333) if scale_selected else 1
        tip=p+world_normal*(size*factor)
        vertices=mesh.faces[face];offset=mesh.face_corners[face].index(i)
        following=om.MPoint(*mesh.points[vertices[(offset+1)%len(vertices)]])*matrix
        previous=om.MPoint(*mesh.points[vertices[offset-1]])*matrix
        normal=om.MVector(*mesh.face_normals[face]).transformAsNormal(matrix).normal()
        origin=p+normal*(size*.02)
        wedge=[origin, origin+(following-p)*wedge_scale, origin+(previous-p)*wedge_scale]
        proxy=om.MPoint(*core.mean([(v.x,v.y,v.z) for v in wedge]))
        if not xray:
            screen=view.worldToView(proxy)
            # Maya API 2.0 fills the supplied output objects; it does not return a pair.
            ray_origin=om.MPoint()
            ray_direction=om.MVector()
            view.viewToWorld(int(screen[0]),int(screen[1]),ray_origin,ray_direction)
            ray_direction.normalize()
            distance=(proxy-ray_origin).length()
            epsilon=max(1e-5,distance*1e-6)
            if distance>epsilon:
                hit=fn.closestIntersection(om.MFloatPoint(ray_origin),om.MFloatVector(ray_direction),
                    om.MSpace.kWorld,max(0,distance-epsilon),False,accelParams=accelerator)
                if hit: continue
        def screen(point):
            value=view.worldToView(point)
            return (float(value[0]),float(value[1]))
        markers[i]=(screen(p),screen(tip),tuple(screen(v) for v in wedge))
    return markers


def topology_selection(session,kind,individual=True):
    mesh,selected=session.select(individual)
    topology=selection.Topology(mesh)
    vertices=sorted({mesh.corner_vertices[i] for i in selected})
    faces=sorted({mesh.corner_faces[i] for i in selected})
    blocked={v for v,corners in enumerate(mesh.vertex_corners) if set(corners)<=session.visibility.hidden}
    blocked_faces={f for f,corners in enumerate(mesh.face_corners) if set(corners)<=session.visibility.hidden}
    if kind=='linked':
        chosen=topology.linked(vertices,blocked)
        result={i for v in chosen for i in mesh.vertex_corners[v]}
    elif kind=='vertex_path':
        if len(vertices)!=2: raise ValueError('Select exactly two endpoint vertices')
        chosen=topology.path(*vertices,blocked=blocked)
        result={i for v in chosen for i in mesh.vertex_corners[v]}
    elif kind=='face_path':
        if len(faces)!=2: raise ValueError('Select corners on exactly two endpoint faces')
        chosen=topology.path(*faces,faces=True,blocked=blocked_faces)
        result={i for f in chosen for i in mesh.face_corners[f]}
    elif kind in ('edge_loop','face_ring'):
        items=cmds.ls(selection=True,long=True,flatten=True) or []
        edges=(cmds.polyListComponentConversion(items,toEdge=True) or []) if items else []
        edges=cmds.ls(edges,flatten=True,long=True) if edges else []
        if len(edges)!=1: raise ValueError('Select exactly one native Maya edge for loop/ring selection')
        index=int(edges[0].rsplit('[',1)[1].rstrip(']'))
        endpoints=tuple(om.MFnMesh(scene.mesh_path(session.shape)).getEdgeVertices(index))
        if kind=='edge_loop':
            chosen=topology.edge_loop(endpoints,blocked)
            result={i for edge in chosen for v in edge for i in mesh.vertex_corners[v]}
        else:
            chosen=topology.face_ring(endpoints,blocked=blocked_faces)
            result={i for f in chosen for i in mesh.face_corners[f]}
    else: raise ValueError('Unknown topology selection')
    session.set_selection(result,active=min(result) if result else None)


class ViewportSelector:
    """Scoped event filter. Alt/middle/right navigation is left to Maya."""
    def __init__(self,panel):
        from .ui import QtCore, QtWidgets
        if QtCore.qVersion().startswith('6'):
            from shiboken6 import wrapInstance
        else:
            from shiboken2 import wrapInstance
        self.panel=panel
        self.session=panel.require()
        self.view=omui.M3dView.active3dView()
        self.widget=wrapInstance(int(self.view.widget()),QtWidgets.QWidget)
        self.path=[];self.markers={};self.base=set();self.mode='click'
        owner=self
        class Filter(QtCore.QObject):
            def eventFilter(self,watched,event):
                try: return owner.event(event)
                except Exception as exc:
                    cmds.warning('Abnormal picker stopped: '+str(exc))
                    from . import tools
                    if tools._INTERACTION is owner: tools.stop()
                    else: owner.stop()
                    return False
        self.filter=Filter(self.widget)
        self.widget.installEventFilter(self.filter)
        self.widget.setFocus()
        # QPainter guide lives on a transparent child; it never captures input.
        class Guide(QtWidgets.QWidget):
            def paintEvent(self,event):
                from .ui import QtGui
                if not owner.path: return
                painter=QtGui.QPainter(self)
                try:
                    painter.setPen(QtGui.QPen(QtGui.QColor(240,190,70),1))
                    ratio_x=owner.view.portWidth()/max(1,owner.widget.width())
                    ratio_y=owner.view.portHeight()/max(1,owner.widget.height())
                    points=[QtCore.QPointF(x/ratio_x,(owner.view.portHeight()-y)/ratio_y) for x,y in owner.path]
                    if owner.mode=='box': painter.drawRect(QtCore.QRectF(points[0],points[-1]).normalized())
                    elif owner.mode=='circle':
                        radius=owner.panel.selection_radius.value()/ratio_x
                        painter.drawEllipse(points[-1],radius,radius)
                    elif len(points)>1: painter.drawPolyline(QtGui.QPolygonF(points))
                finally: painter.end()
        self.guide=Guide(self.widget)
        self.guide.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents,True)
        self.guide.setAttribute(QtCore.Qt.WA_TranslucentBackground,True)
        self.guide.setGeometry(self.widget.rect());self.guide.show()

    def event(self,event):
        from .ui import QtCore
        kind=event.type()
        if kind==QtCore.QEvent.KeyPress:
            return self.key(event)
        if kind not in (QtCore.QEvent.MouseButtonPress,QtCore.QEvent.MouseMove,QtCore.QEvent.MouseButtonRelease): return False
        if event.modifiers() & QtCore.Qt.AltModifier:
            if self.path:
                self.path=[];self.session.preview_selection=None;self.guide.update()
            return False
        if kind==QtCore.QEvent.MouseButtonPress and event.button()==QtCore.Qt.LeftButton:
            try:
                self.mode=self.panel.selection_mode.currentText().lower()
                self.markers=project(self.session,self.panel.individual.isChecked(),
                    self.panel.normal_size.value(),self.panel.overlay_xray.isChecked(),
                    self.panel.overlay_scale_selected.isChecked(),self.panel.overlay_selected_only.isChecked(),view=self.view,wedge_scale=self.panel.overlay_wedge_scale.value())
                self.base=scene.selected_corners(self.session.shape,self.session.current(),
                    self.panel.individual.isChecked(),allow_empty=True)
                self.session.record()
                self.path=[self.point(event)]
                self.modifiers=event.modifiers()
                self.guide.setGeometry(self.widget.rect());self.guide.update()
            except Exception as exc:
                self.path=[];cmds.warning('Abnormal selection: '+str(exc))
            return True
        if kind==QtCore.QEvent.MouseMove and self.path:
            point=self.point(event)
            if self.mode=='box': self.path=self.path[:1]+[point]
            else: self.path.append(point)
            hits=selection.choose(self.markers,self.mode,self.path,radius=self.panel.selection_radius.value())
            shift=bool(self.modifiers & QtCore.Qt.ShiftModifier)
            control=bool(self.modifiers & QtCore.Qt.ControlModifier)
            mode='toggle' if shift and control else 'add' if shift else 'subtract' if control else 'replace'
            preview=selection.combine(self.base,hits,mode)
            if not self.panel.individual.isChecked():
                mesh=self.session.current()
                preview={i for j in preview for i in mesh.vertex_corners[mesh.corner_vertices[j]]}
            self.session.preview_selection=preview
            self.panel.refresh_overlay()
            self.guide.update();return True
        if kind==QtCore.QEvent.MouseButtonRelease and event.button()==QtCore.Qt.LeftButton and self.path:
            try:
                self.path.append(self.point(event))
                hits=selection.choose(self.markers,self.mode,self.path,radius=self.panel.selection_radius.value())
                shift=bool(self.modifiers & QtCore.Qt.ShiftModifier)
                control=bool(self.modifiers & QtCore.Qt.ControlModifier)
                mode='toggle' if shift and control else 'add' if shift else 'subtract' if control else 'replace'
                result=selection.combine(self.base,hits,mode)
                if not self.panel.individual.isChecked():
                    mesh=self.session.current()
                    result={i for j in result for i in mesh.vertex_corners[mesh.corner_vertices[j]]}
                self.session.preview_selection=None
                self.session.set_selection(result,active=min(hits) if hits else None)
                self.panel.refresh_overlay()
            except Exception as exc: cmds.warning('Abnormal selection: '+str(exc))
            self.session.preview_selection=None
            self.path=[];self.guide.update();return True
        return False

    def point(self,event):
        p=event.position() if hasattr(event,'position') else event.pos()
        return (p.x()*self.view.portWidth()/max(1,self.widget.width()),
                self.view.portHeight()-p.y()*self.view.portHeight()/max(1,self.widget.height()))

    def key(self,event):
        from .ui import QtCore
        key=event.key();control=bool(event.modifiers() & QtCore.Qt.ControlModifier)
        shift=bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        if key in (QtCore.Qt.Key_Q,QtCore.Qt.Key_Escape):
            if self.path:
                self.path=[];self.session.preview_selection=None;self.guide.update()
            else:
                from . import tools
                tools.stop()
            return True
        if self.path: return True  # Finish/cancel the region gesture before other actions.
        if not self.panel.shortcuts_enabled.isChecked(): return False
        if key in (QtCore.Qt.Key_BracketLeft,QtCore.Qt.Key_BracketRight):
            self.panel.selection_radius.setValue(self.panel.selection_radius.value()+(5 if key==QtCore.Qt.Key_BracketRight else -5));return True
        if control and key==QtCore.Qt.Key_Z:
            self.panel.run(lambda:self.session.history_step(1 if shift else -1));return True
        if key==QtCore.Qt.Key_H and event.modifiers() & QtCore.Qt.AltModifier:
            self.panel.run(self.panel.reveal_normals);return True
        if key==QtCore.Qt.Key_L and shift:
            self.panel.selection_mode.setCurrentText('Lasso');return True
        actions={QtCore.Qt.Key_A: self.panel.select_all,
                 QtCore.Qt.Key_H:lambda:self.panel.hide_normals(shift),
                 QtCore.Qt.Key_F:self.panel.reveal_normals,
                 QtCore.Qt.Key_L:lambda:topology_selection(self.session,'linked',self.panel.individual.isChecked())}
        modes={QtCore.Qt.Key_B:'Box',QtCore.Qt.Key_C:'Circle'}
        if key in modes:
            self.panel.selection_mode.setCurrentText(modes[key]);return True
        if key in actions:
            self.panel.run(actions[key]);return True
        return False

    def stop(self):
        self.session.preview_selection=None
        try:
            self.widget.removeEventFilter(self.filter)
            self.guide.close();self.guide.deleteLater();self.filter.deleteLater()
        except RuntimeError: pass
