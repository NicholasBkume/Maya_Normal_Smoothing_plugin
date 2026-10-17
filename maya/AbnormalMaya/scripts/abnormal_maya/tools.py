"""Maya native dragger context for interactive normal rotation.

The dragger's step undo mode groups a press/drag/release gesture. A selection
and baseline are captured at press; previews are absolute, never compounded.
"""
import math
from maya import cmds
from . import scene

_CONTEXT = 'abnormalNormalRotateContext'
_TOOL = None
_INTERACTION = None


class RotateTool:
    def __init__(self, session, axis, space, individual, auto_mirror):
        self.session = session
        self.axis = axis
        self.space = space
        self.individual = individual
        self.auto_mirror = auto_mirror
        self.baseline = None
        self.selection = None
        self.origin = None

    def press(self):
        try:
            self.session.record()
            mesh, _ = self.session.select(self.individual)
            self.baseline = list(mesh.normals)
            self.selection = cmds.ls(selection=True, long=True, flatten=True) or []
            self.origin = cmds.draggerContext(_CONTEXT, query=True, anchorPoint=True)
        except Exception as exc:
            self.baseline = None
            cmds.warning('Abnormal rotation: ' + str(exc))

    def drag(self):
        if self.baseline is None:
            return
        try:
            if (cmds.ls(selection=True, long=True, flatten=True) or []) != self.selection:
                raise RuntimeError('Selection changed during normal rotation')
            point = cmds.draggerContext(_CONTEXT, query=True, dragPoint=True)
            angle = math.radians((point[0] - self.origin[0]) * .5)
            self.session.apply('rotate', axis=self.axis, angle=angle,
                               space=self.space, individual=self.individual,
                               auto_mirror=self.auto_mirror, baseline=self.baseline,record_history=False)
            cmds.refresh(force=True)
        except Exception as exc:
            cmds.warning('Abnormal rotation stopped: ' + str(exc))
            self.baseline = None

    def release(self):
        try:
            if self.baseline is not None: self.session.record()
        except Exception as exc: cmds.warning('Abnormal rotation history: '+str(exc))
        finally:
            self.baseline = None
            self.selection = None

    def finalize(self):
        # Leaving the tool keeps edits; use Maya Undo or Cancel Session.
        self.release()


def rotate(session, axis=(0, 1, 0), space='Object', individual=True, auto_mirror=()):
    global _TOOL
    stop()
    if cmds.draggerContext(_CONTEXT, exists=True):
        if cmds.currentCtx() == _CONTEXT:
            cmds.setToolTo('selectSuperContext')
        cmds.deleteUI(_CONTEXT)
    _TOOL = RotateTool(session, axis, space, individual, auto_mirror)
    cmds.draggerContext(_CONTEXT, pressCommand=_TOOL.press, dragCommand=_TOOL.drag,
                       releaseCommand=_TOOL.release, finalize=_TOOL.finalize,
                       cursor='crossHair', space='screen', undoMode='step',
                       drawString='Abnormal: drag horizontally to rotate normals; Q exits; Undo restores gesture')
    cmds.setToolTo(_CONTEXT)


def stop():
    global _INTERACTION
    interaction=_INTERACTION
    _INTERACTION=None
    if interaction is not None:
        try: interaction.stop()
        except Exception as exc: cmds.warning('Abnormal tool stopped but could not restore its state: '+str(exc))
    if cmds.currentCtx() == _CONTEXT:
        cmds.setToolTo('selectSuperContext')


def pick(panel):
    global _INTERACTION
    stop()
    from .picking import ViewportSelector
    _INTERACTION=ViewportSelector(panel)
    return _INTERACTION


def manipulate(panel,mode):
    global _INTERACTION
    stop()
    from .manipulation import Manipulation
    _INTERACTION=Manipulation(panel,mode)
    return _INTERACTION


def finish_manipulation(keep):
    global _INTERACTION
    interaction=_INTERACTION
    if interaction is None or not getattr(interaction,'is_manipulation',False):
        raise ValueError('No live manipulation is running')
    _INTERACTION=None
    interaction.finish(keep)
