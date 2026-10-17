import math
import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'AbnormalMaya' / 'scripts'))
from abnormal_maya import core


def fixture():
    return core.Mesh([(-1,0,0), (1,0,0), (0,1,0), (0,-1,0)],
                     [[0,1,2], [1,0,3]],
                     [(0,0,1)]*3 + [(0,1,0)]*3,
                     [(0,0,1), (0,0,1)])


class NormalTests(unittest.TestCase):
    def assertVector(self, actual, expected):
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=7)

    def test_split_corners_not_collapsed(self):
        mesh = fixture()
        result = core.edit(mesh, {0}, 'flip')
        self.assertVector(result[0], (0,0,-1))
        self.assertEqual(result[4], mesh.normals[4])
        self.assertEqual(mesh.normals[0], (0,0,1))

    def test_flatten_degenerate_keeps_original(self):
        mesh = fixture()
        result = core.edit(mesh, {0}, 'flatten', axis=(0,0,1))
        self.assertVector(result[0], mesh.normals[0])

    def test_average_vertex_preserves_other_vertices(self):
        mesh = fixture()
        result = core.edit(mesh, {0,4}, 'average_vertex')
        expected = core.unit((0,1,1))
        self.assertVector(result[0], expected)
        self.assertVector(result[4], expected)
        self.assertEqual(result[1], mesh.normals[1])

    def test_opposing_average_does_not_nan(self):
        mesh = fixture()
        mesh.normals[1] = (0,0,-1)
        result = core.edit(mesh, {0,1}, 'average')
        self.assertEqual(result, mesh.normals)

    def test_weight_zero_and_half(self):
        mesh = fixture()
        self.assertEqual(core.edit(mesh, {0}, 'align', weights={}), mesh.normals)
        result = core.edit(mesh, {0}, 'align', weights={0:0.5})
        self.assertVector(result[0], core.unit((0,1,1)))

    def test_rotation(self):
        result = core.edit(fixture(), {0}, 'rotate', axis=(1,0,0), angle=math.pi/2)
        self.assertVector(result[0], (0,-1,0))

    def test_smoothing_matches_neighbor_corner_mean_and_touches_siblings(self):
        mesh = fixture()
        # Vertex 0's neighbors: 1 (two corners), 2, 3; mean = (0,.5,.5).
        result = core.edit(mesh, {0}, 'smooth', strength=1, iterations=1)
        self.assertVector(result[0], core.unit((0,.25,.75)))
        self.assertVector(result[4], core.unit((0,.75,.25)))
        self.assertEqual(result[1], mesh.normals[1])

    def test_from_faces_requires_fully_selected_face(self):
        mesh = fixture()
        self.assertEqual(core.edit(mesh, {0,1}, 'from_faces'), mesh.normals)
        result = core.edit(mesh, {3,4,5}, 'from_faces', individual=True)
        self.assertVector(result[3], (0,0,1))
        self.assertEqual(result[0], mesh.normals[0])

    def test_inside_respects_sign(self):
        mesh = fixture()
        self.assertVector(core.edit(mesh, {0}, 'inside')[0], (0,0,-1))

    def test_inside_outside_averaging_is_independent_of_corner_selection_mode(self):
        mesh = fixture()
        mesh.face_normals = [(1,0,0), (0,0,1)]
        result = core.edit(mesh, {0,4}, 'outside', individual=True)
        self.assertVector(result[0], core.unit((1,0,1)))
        flat = core.edit(mesh, {0,4}, 'outside', smooth_shading=False)
        self.assertVector(flat[0], (1,0,0))
        self.assertVector(flat[4], (0,0,1))

    def test_point_and_sphere_opposite(self):
        mesh = fixture()
        point = core.edit(mesh, {0}, 'point', target=(0,0,0), strength=1)
        sphere = core.edit(mesh, {0}, 'sphere', target=(0,0,0), strength=1)
        self.assertVector(point[0], (1,0,0))
        self.assertVector(sphere[0], (-1,0,0))

    def test_target_distance_affects_partial_strength(self):
        mesh = fixture()
        result = core.edit(mesh, {0}, 'point', target=(3,0,0), strength=.5)
        self.assertVector(result[0], core.unit((2,0,.5)))

    def test_point_align_uses_corner_centroid(self):
        mesh = fixture()
        result = core.edit(mesh, {0,1}, 'point', target=(0,2,0), strength=1, align=True)
        self.assertVector(result[0], (0,1,0))
        self.assertVector(result[1], (0,1,0))

    def test_mirror_reflects_destination_and_does_not_mutate_input(self):
        normals = [(1,0,0), (0,1,0)]
        result = core.mirror(normals, {0}, {0:1}, 0)
        self.assertEqual(result, [(1,0,0), (-1,0,0)])
        self.assertEqual(normals[1], (0,1,0))

    def test_mirror_tolerance(self):
        mesh = fixture()
        mesh.points[1] = (4,0,0)
        self.assertNotIn(0, core.mirror_map(mesh, 0, .01))
        self.assertIn(0, core.mirror_map(mesh, 0))

    def test_clipboard_references_current_source(self):
        mesh = fixture()
        mesh.normals[0] = (1,0,0)
        result = core.paste(mesh, {1}, [0])
        self.assertEqual(result[1], (1,0,0))
        self.assertEqual(result[0], mesh.normals[0])

    def test_color_normal_decode_preserves_signed_corner_order(self):
        result = core.normals_from_colors([(0,0,-1,1), (-1,0,0,1), (0,2,0,1)], 3)
        self.assertEqual(result, [(0,0,-1), (-1,0,0), (0,1,0)])

    def test_color_normal_decode_rejects_missing_or_corrupt_data(self):
        for colors, count in [([],1), ([(0,0,0,1)],1), ([(-1,-1,-1,-1)],1),
                              ([(float('nan'),0,1,1)],1), ([(1,0)],1)]:
            with self.assertRaises(ValueError):
                core.normals_from_colors(colors, count)

    def test_reset(self):
        mesh = fixture()
        result = core.edit(mesh, {0}, 'reset', reference=[(1,0,0)]*6)
        self.assertEqual(result[0], (1,0,0))
        self.assertEqual(result[1], mesh.normals[1])

    def test_invalid_selection_and_operation(self):
        for selected in (set(), {-1}, {100}):
            with self.assertRaises(ValueError):
                core.edit(fixture(), selected, 'flip')
        with self.assertRaises(ValueError):
            core.edit(fixture(), {0}, 'unknown')

    def test_kdtree_against_brute_force(self):
        rng = random.Random(42)
        points = [tuple(rng.uniform(-5,5) for _ in range(3)) for _ in range(80)]
        tree = core.KDTree(points)
        for _ in range(40):
            target = tuple(rng.uniform(-5,5) for _ in range(3))
            expected = min(range(len(points)), key=lambda i: (core.dot(core.sub(points[i],target),core.sub(points[i],target)),i))
            self.assertEqual(tree.nearest(target)[0], expected)

    def test_all_operations_return_finite_unit_normals(self):
        mesh = fixture()
        for operation in ('flip','flatten','align','rotate','average','average_vertex',
                          'smooth','from_faces','outside','inside','point','sphere'):
            result = core.edit(mesh, set(range(6)), operation, angle=.4)
            for normal in result:
                self.assertTrue(all(math.isfinite(x) for x in normal))
                self.assertAlmostEqual(core.dot(normal,normal), 1)


if __name__ == '__main__':
    unittest.main()
