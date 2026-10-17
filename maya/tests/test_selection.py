import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AbnormalMaya'/'scripts'))
from abnormal_maya import core,selection


def grid(width=3,height=3):
    points=[(x,y,0) for y in range(height) for x in range(width)]
    faces=[]
    for y in range(height-1):
        for x in range(width-1):
            a=y*width+x
            faces.append([a,a+1,a+1+width,a+width])
    return core.Mesh(points,faces,[(0,0,1)]*(4*len(faces)),[(0,0,1)]*len(faces))


class SelectionTests(unittest.TestCase):
    def test_click_prefers_corner_wedge_over_overlapping_normal(self):
        markers={0:((0,0),(0,10),((0,0),(3,0),(0,3))),
                 1:((1,0),(1,10),((10,10),(11,10),(10,11)))}
        self.assertEqual(selection.choose(markers,'click',[(1,1)]),{0})

    def test_click_outside_tolerance_does_not_select(self):
        markers={0:((0,0),(0,10),((0,0),(1,0),(0,1)))}
        self.assertEqual(selection.choose(markers,'click',[(100,100)]),set())

    def test_box_circle_and_lasso_match_centroid(self):
        markers={0:((0,0),(0,10),((0,0),(3,0),(0,3))),
                 1:((20,20),(20,30),((20,20),(23,20),(20,23)))}
        self.assertEqual(selection.choose(markers,'box',[(5,5),(-1,-1)]),{0})
        self.assertEqual(selection.choose(markers,'circle',[(0,0),(20,20)],radius=2),{0,1})
        self.assertEqual(selection.choose(markers,'lasso',[(-1,-1),(5,-1),(5,5),(-1,5)]),{0})

    def test_concave_lasso_and_boundary(self):
        polygon=[(0,0),(3,0),(3,1),(1,1),(1,3),(0,3)]
        self.assertTrue(selection.in_polygon((.5,2),polygon))
        self.assertFalse(selection.in_polygon((2,2),polygon))
        self.assertTrue(selection.in_polygon((0,1),polygon))
        self.assertFalse(selection.in_polygon((0,0),[(1,1)]))

    def test_combination_modes(self):
        self.assertEqual(selection.combine({0,1},{1,2},'replace'),{1,2})
        self.assertEqual(selection.combine({0,1},{1,2},'add'),{0,1,2})
        self.assertEqual(selection.combine({0,1},{1,2},'subtract'),{0})
        self.assertEqual(selection.combine({0,1},{1,2},'toggle'),{0,2})

    def test_linked_excludes_disconnected_and_hidden_vertices(self):
        mesh=grid()
        mesh.points.append((9,9,9));mesh.vertex_corners.append([]);mesh.neighbors.append(set())
        graph=selection.Topology(mesh)
        self.assertEqual(graph.linked({0}),set(range(9)))
        self.assertNotIn(8,graph.linked({0},blocked={5,7,8}))

    def test_vertex_path_unweighted_deterministic_and_blocked(self):
        graph=selection.Topology(grid())
        path=graph.path(0,8)
        self.assertEqual(len(path),5)
        self.assertEqual(path[0],0);self.assertEqual(path[-1],8)
        self.assertNotIn(1,graph.path(0,8,blocked={1}))
        with self.assertRaises(ValueError): graph.path(0,8,blocked={1,3})

    def test_face_path_follows_shared_edges(self):
        self.assertEqual(selection.Topology(grid()).path(0,3,faces=True),[0,1,3])

    def test_edge_loop_stops_at_non_valence_four_boundary(self):
        graph=selection.Topology(grid(4,4))
        self.assertEqual(graph.edge_loop((1,5)),{(1,5),(5,9),(9,13)})
        self.assertEqual(graph.edge_loop((1,5),blocked={9}),{(1,5)})

    def test_quad_face_ring_crosses_opposite_edges(self):
        graph=selection.Topology(grid(4,4))
        self.assertEqual(graph.face_ring((1,5)),{0,1,2})
        self.assertEqual(graph.face_ring((1,5),blocked={1}),{0})

    def test_angle_wraps_and_preserves_sign(self):
        self.assertAlmostEqual(selection.ring_angle((1,0),(0,1),(0,0)),math.pi/2)
        self.assertAlmostEqual(selection.ring_angle((-1,.001),(-1,-.001),(0,0)),.002,places=5)


if __name__=='__main__': unittest.main()
