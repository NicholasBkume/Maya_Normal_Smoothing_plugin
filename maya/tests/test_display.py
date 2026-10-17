import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AbnormalMaya'/'scripts'))
from abnormal_maya import core, display


def fixture():
    return core.Mesh([(0,0,0),(1,0,0),(0,1,0)],[[0,1,2]],
                     [(0,0,1)]*3,[(0,0,1)])


def geometry(batches, kind):
    return [vertex for primitive,color,vertices in batches if primitive == kind for vertex in vertices]


class DisplayTests(unittest.TestCase):
    def test_three_corners_keep_distinct_lines(self):
        result = display.batches(fixture(),scale_selected=False,size=2)
        self.assertEqual(len(geometry(result,'lines')),6)
        self.assertEqual(geometry(result,'lines')[:2],[(0,0,0),(0,0,2)])

    def test_selected_only_and_hidden_are_intersected(self):
        result=display.batches(fixture(),selected={0,1},hidden={1},selected_only=True)
        self.assertEqual(len(geometry(result,'lines')),2)
        self.assertEqual(len(geometry(result,'points')),1)

    def test_active_color_and_source_scale_factors(self):
        result=display.batches(fixture(),selected={0,1},active={0},size=1)
        lines={color:vertices for primitive,color,vertices in result if primitive=='lines'}
        self.assertEqual(lines[display.PALETTE['active']][1],(0,0,1))
        self.assertEqual(lines[display.PALETTE['selected']][1],(1,0,.666))
        self.assertEqual(lines[display.PALETTE['normal']][1],(0,1,.333))

    def test_weights_red_at_one_and_do_not_change_input(self):
        weights={0:1}
        result=display.batches(fixture(),weights=weights,draw_weights=True)
        red=[vertices for primitive,color,vertices in result if primitive=='lines' and color==(1,0,0,1)]
        self.assertEqual(len(red),1)
        self.assertEqual(weights,{0:1})

    def test_corner_wedge_uses_incident_edges_and_face_offset(self):
        result=display.batches(fixture(),selected={0},selected_only=True,wedges=True,size=1,wedge_scale=.25)
        self.assertEqual(geometry(result,'triangles'),[(0,0,.02),(.25,0,.02),(0,.25,.02)])

    def test_options_do_not_mutate_normals_or_topology(self):
        mesh=fixture()
        expected=list(mesh.normals)
        display.batches(mesh,wedges=True,weights={},draw_weights=True)
        self.assertEqual(mesh.normals,expected)
        self.assertEqual(mesh.faces,[[0,1,2]])

    def test_no_points_when_disabled(self):
        self.assertEqual(geometry(display.batches(fixture(),points=False),'points'),[])

    def test_hide_selection_reveal_and_local_history(self):
        state=display.Visibility(6)
        state.hide({1,2})
        self.assertEqual(state.hidden,{1,2})
        state.hide({0,3},unselected=True)
        self.assertEqual(state.hidden,{1,2,4,5})
        state.undo()
        self.assertEqual(state.hidden,{1,2})
        state.redo()
        self.assertEqual(state.hidden,{1,2,4,5})
        state.reveal()
        self.assertEqual(state.hidden,set())
        state.undo()
        self.assertEqual(state.hidden,{1,2,4,5})

    def test_visibility_redo_branch_discarded(self):
        state=display.Visibility(3)
        state.hide({0})
        state.hide({1})
        state.undo()
        state.hide({2})
        state.redo()
        self.assertEqual(state.hidden,{0,2})

    def test_history_is_bounded_and_does_not_alias_hidden_set(self):
        state=display.Visibility(3)
        for _ in range(200):
            state.hide({0})
            state.reveal()
        self.assertLessEqual(len(state._history),128)
        state.hidden.add(2)
        state.undo()
        self.assertNotIn(2,state.hidden)

    def test_invalid_corner_rejected(self):
        with self.assertRaises(ValueError):
            display.Visibility(2).hide({5})


if __name__=='__main__':
    unittest.main()
