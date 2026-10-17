import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AbnormalMaya'/'scripts'))
from abnormal_maya import render


class Manager:
    def __init__(self, fail=None):
        self.calls=[]
        self.fail=fail
    def beginDrawable(self, selection): self.calls.append(('begin',selection))
    def endDrawable(self): self.calls.append(('end',))
    def beginDrawInXray(self): self.calls.append(('xray_begin',))
    def endDrawInXray(self): self.calls.append(('xray_end',))
    def setLineWidth(self, value): pass
    def setPointSize(self, value): pass
    def setColor(self, value): pass
    # Deliberately no draw2D defaults: catches the Maya 2025 failure.
    def lineList(self, vertices, draw2D): self.calls.append(('lines',draw2D))
    def points(self, vertices, draw2D):
        self.calls.append(('points',draw2D))
        if self.fail: raise RuntimeError('simulated native draw failure')
    def mesh(self, primitive, vertices): self.calls.append(('mesh',primitive))


class RenderTests(unittest.TestCase):
    def test_explicit_world_space_flag_for_lines_and_points(self):
        manager=Manager()
        batches=[('lines',(1,0,0,1),[(0,0,0),(1,0,0)]),
                 ('points',(1,0,0,1),[(0,0,0)]),
                 ('triangles',(1,0,0,.3),[(0,0,0),(1,0,0),(0,1,0)])]
        render.draw(manager,batches,nonselectable=7,triangles=9)
        self.assertEqual(manager.calls,[('begin',7),('lines',False),('points',False),('mesh',9),('end',)])

    def test_xray_scopes_close_after_native_failure(self):
        manager=Manager(fail=True)
        with self.assertRaises(RuntimeError):
            render.draw(manager,[('points',(1,1,1,1),[(0,0,0)])],xray=True)
        self.assertEqual(manager.calls[-2:],[('xray_end',),('end',)])

    def test_no_xray_calls_when_disabled(self):
        manager=Manager()
        render.draw(manager,[])
        self.assertEqual(manager.calls,[('begin',0),('end',)])


if __name__=='__main__': unittest.main()
