"""Viewport 2.0 Python draw plugin, loaded on demand by abnormal_maya.overlay.

Local prototype node ID: 0x0007F7F0. Obtain a registered Autodesk ID before
third-party studio-wide distribution; initialization fails on ID collisions.
"""
from maya.api import OpenMaya as om
from maya.api import OpenMayaUI as omui
from maya.api import OpenMayaRender as omr
from abnormal_maya import overlay

TYPE_ID = om.MTypeId(0x0007F7F0)
CLASSIFICATION = 'drawdb/geometry/abnormalNormalOverlay'
REGISTRANT = 'AbnormalNormalOverlayDraw'


def maya_useNewAPI():
    pass


class OverlayNode(omui.MPxLocatorNode):
    key_attribute = None

    def postConstructor(self):
        self.setDoNotWrite(True)

    def isBounded(self):
        return False

    @staticmethod
    def creator():
        return OverlayNode()

    @staticmethod
    def initialize():
        attr = om.MFnTypedAttribute()
        OverlayNode.key_attribute = attr.create('overlayKey','ovk',om.MFnData.kString)
        attr.hidden = True
        OverlayNode.addAttribute(OverlayNode.key_attribute)


class DrawData(om.MUserData):
    def __init__(self):
        super().__init__(False)
        self.batches = ()
        self.xray = False
        self.point_size = 4.0
        self.line_width = 1.5


class OverlayDraw(omr.MPxDrawOverride):
    def __init__(self, obj):
        super().__init__(obj, None, False)

    @staticmethod
    def creator(obj):
        return OverlayDraw(obj)

    def supportedDrawAPIs(self):
        return omr.MRenderer.kAllDevices

    def isBounded(self, obj_path, camera_path):
        return False

    def transform(self, obj_path, camera_path):
        # Payload positions are already world-space, including transformed
        # normals. Do not apply the source DAG transform a second time.
        return om.MMatrix()

    def hasUIDrawables(self):
        return True

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        data = old_data if isinstance(old_data,DrawData) else DrawData()
        key = om.MFnDependencyNode(obj_path.node()).findPlug('overlayKey',False).asString()
        payload = overlay.PAYLOADS.get(key, ((),False,4.0,1.5))
        geometry, data.xray, data.point_size, data.line_width = payload
        data.batches = tuple((kind,om.MColor(color),
                              om.MPointArray([om.MPoint(*p) for p in vertices]))
                             for kind,color,vertices in geometry)
        return data

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        if not isinstance(data,DrawData):
            return
        draw_manager.beginDrawable(omr.MUIDrawManager.kNonSelectable)
        xray_started = False
        try:
            if data.xray:
                draw_manager.beginDrawInXray()
                xray_started = True
            draw_manager.setLineWidth(data.line_width)
            draw_manager.setPointSize(data.point_size)
            for kind,color,vertices in data.batches:
                draw_manager.setColor(color)
                if kind == 'lines':
                    draw_manager.lineList(vertices)
                elif kind == 'points':
                    draw_manager.points(vertices)
                else:
                    draw_manager.mesh(omr.MUIDrawManager.kTriangles,vertices)
        finally:
            try:
                if xray_started:
                    draw_manager.endDrawInXray()
            finally:
                draw_manager.endDrawable()


def initializePlugin(obj):
    plugin = om.MFnPlugin(obj,'Abnormal Maya contributors','0.2.0','Any')
    plugin.registerNode(overlay.NODE_TYPE,TYPE_ID,OverlayNode.creator,OverlayNode.initialize,
                        om.MPxNode.kLocatorNode,CLASSIFICATION)
    try:
        omr.MDrawRegistry.registerDrawOverrideCreator(CLASSIFICATION,REGISTRANT,OverlayDraw.creator)
    except Exception:
        plugin.deregisterNode(TYPE_ID)
        raise


def uninitializePlugin(obj):
    omr.MDrawRegistry.deregisterDrawOverrideCreator(CLASSIFICATION,REGISTRANT)
    om.MFnPlugin(obj).deregisterNode(TYPE_ID)
