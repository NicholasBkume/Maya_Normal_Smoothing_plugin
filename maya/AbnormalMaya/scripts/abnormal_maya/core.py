"""Host-independent face-corner normal algorithms derived from Abnormal (MIT).

Vectors and positions are object-space triples. Corner order is face-major.
No Maya or NumPy dependency, so numerical behavior can be tested outside Maya.
"""
from dataclasses import dataclass
import math

EPSILON = 1e-12


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, factor):
    return tuple(x * factor for x in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def unit(v, fallback=(0.0, 1.0, 0.0)):
    length = math.sqrt(dot(v, v))
    if length <= EPSILON:
        return tuple(fallback)
    return mul(v, 1.0 / length)


def mean(vectors, fallback=(0.0, 1.0, 0.0)):
    vectors = list(vectors)
    if not vectors:
        return tuple(fallback)
    return tuple(sum(v[a] for v in vectors) / len(vectors) for a in range(3))


def rotate(vector, axis, angle):
    """Rodrigues rotation; angle in radians."""
    axis = unit(axis)
    c, s = math.cos(angle), math.sin(angle)
    return add(add(mul(vector, c), mul(cross(axis, vector), s)),
               mul(axis, dot(axis, vector) * (1-c)))


@dataclass
class Mesh:
    points: list
    faces: list
    normals: list
    face_normals: list

    def __post_init__(self):
        self.corner_vertices = []
        self.corner_faces = []
        self.vertex_corners = [[] for _ in self.points]
        self.neighbors = [set() for _ in self.points]
        self.face_corners = []
        self.tangents = []
        for face_id, vertices in enumerate(self.faces):
            corners = []
            for offset, vertex in enumerate(vertices):
                index = len(self.corner_vertices)
                corners.append(index)
                self.corner_vertices.append(vertex)
                self.corner_faces.append(face_id)
                self.vertex_corners[vertex].append(index)
                previous, following = vertices[offset-1], vertices[(offset+1) % len(vertices)]
                self.neighbors[vertex].update((previous, following))
                p = self.points[vertex]
                self.tangents.append(unit(add(unit(sub(self.points[previous], p), (0, 0, 0)),
                                              unit(sub(self.points[following], p), (0, 0, 0)))))
            self.face_corners.append(corners)
        if len(self.normals) != len(self.corner_vertices):
            raise ValueError('Expected exactly one normal per face corner')

    @property
    def signature(self):
        return (len(self.points), tuple(tuple(face) for face in self.faces))


def edit(mesh, selected, operation, axis=(0, 1, 0), angle=0.0,
         strength=0.25, iterations=5, target=(0, 0, 0), align=False,
         individual=True, smooth_shading=True, reference=None, weights=None):
    """Return a full new corner-normal array without mutating the mesh.

    Smooth matches the source: all corners at touched vertices are updated;
    neighbor corner means are recomputed each iteration; normalize at the end.
    Weights are a corner->weight dictionary. None means no filter; an empty
    dictionary explicitly protects every corner (fixes the source zero mask).
    """
    selected = set(selected)
    if not selected or not selected.issubset(range(len(mesh.normals))):
        raise ValueError('Select at least one valid face corner')
    if not 0 <= strength <= 1 or not 1 <= iterations <= 100:
        raise ValueError('Strength must be 0..1 and iterations 1..100')
    old = list(mesh.normals)
    result = list(old)
    touched = {mesh.corner_vertices[i] for i in selected}
    affected = set(selected)
    if operation == 'average_vertex':
        for vertex in touched:
            group = selected.intersection(mesh.vertex_corners[vertex])
            average = mean(old[i] for i in group)
            for i in group:
                result[i] = average
    elif operation == 'average':
        average = mean(old[i] for i in selected)
        for i in selected:
            result[i] = average
    elif operation == 'smooth':
        affected = {i for v in touched for i in mesh.vertex_corners[v]}
        for _ in range(iterations):
            previous = list(result)
            for vertex in touched:
                adjacent = [i for v in mesh.neighbors[vertex] for i in mesh.vertex_corners[v]]
                if not adjacent:
                    continue
                average = mean(previous[i] for i in adjacent)
                for i in mesh.vertex_corners[vertex]:
                    result[i] = add(mul(previous[i], 1-strength*0.5),
                                    mul(average, strength*0.5))
    elif operation == 'from_faces':
        full_faces = {f for f, corners in enumerate(mesh.face_corners)
                      if set(corners).issubset(selected)}
        affected = set()
        for vertex in touched:
            source = [i for i in mesh.vertex_corners[vertex]
                      if mesh.corner_faces[i] in full_faces]
            if not source:
                continue
            average = mean(mesh.face_normals[mesh.corner_faces[i]] for i in source)
            destinations = source if individual else mesh.vertex_corners[vertex]
            for i in destinations:
                result[i] = average
                affected.add(i)
    elif operation in ('outside', 'inside'):
        sign = 1 if operation == 'outside' else -1
        for i in selected:
            group = selected.intersection(mesh.vertex_corners[mesh.corner_vertices[i]])
            normal = mean(mesh.face_normals[mesh.corner_faces[j]] for j in group) if smooth_shading else mesh.face_normals[mesh.corner_faces[i]]
            result[i] = mul(normal, sign)
    else:
        centroid = mean(mesh.points[mesh.corner_vertices[i]] for i in selected)
        for i in selected:
            n = old[i]
            if operation == 'flip':
                value = mul(n, -1)
            elif operation == 'flatten':
                a = unit(axis)
                value = sub(n, mul(a, dot(n, a)))
            elif operation == 'align':
                value = unit(axis)
            elif operation == 'rotate':
                value = rotate(n, axis, angle)
            elif operation == 'reset':
                if reference is None or len(reference) != len(old):
                    raise ValueError('A matching session snapshot is required')
                value = reference[i]
            elif operation in ('point', 'sphere'):
                p = centroid if align and operation == 'point' else mesh.points[mesh.corner_vertices[i]]
                direction = sub(target, p) if operation == 'point' else sub(p, target)
                value = add(mul(n, 1-strength), mul(direction, strength))
            else:
                raise ValueError('Unknown operation: ' + operation)
            result[i] = value
    return blend(old, result, affected, weights)


def blend(old, new, affected, weights=None):
    result = list(old)
    for i in affected:
        w = 1.0 if weights is None else max(0.0, min(1.0, weights.get(i, 0.0)))
        result[i] = unit(add(mul(old[i], 1-w), mul(new[i], w)), old[i])
    return result


class KDTree:
    """Small dependency-free nearest-vertex index for symmetry."""
    def __init__(self, points):
        self.points = points
        def build(indices, depth):
            if not indices:
                return None
            axis = depth % 3
            indices.sort(key=lambda i: (points[i][axis], i))
            middle = len(indices) // 2
            return (indices[middle], axis, build(indices[:middle], depth+1),
                    build(indices[middle+1:], depth+1))
        self.root = build(list(range(len(points))), 0)

    def nearest(self, point):
        best = [float('inf'), -1]
        def visit(node):
            if node is None:
                return
            index, axis, left, right = node
            distance = dot(sub(point, self.points[index]), sub(point, self.points[index]))
            if (distance, index) < tuple(best):
                best[:] = [distance, index]
            delta = point[axis] - self.points[index][axis]
            visit(left if delta < 0 else right)
            if delta * delta <= best[0]:
                visit(right if delta < 0 else left)
        visit(self.root)
        return best[1], math.sqrt(best[0])


def mirror_map(mesh, axis=0, tolerance=None):
    tree = KDTree(mesh.points)
    mapping = {}
    for i, vertex in enumerate(mesh.corner_vertices):
        point = list(mesh.points[vertex])
        point[axis] *= -1
        match, distance = tree.nearest(point)
        if match < 0 or (tolerance is not None and distance > tolerance):
            continue
        tangent = list(mesh.tangents[i])
        tangent[axis] *= -1
        candidates = mesh.vertex_corners[match]
        if candidates:
            mapping[i] = max(candidates, key=lambda j: (dot(tangent, mesh.tangents[j]), -j))
    return mapping


def mirror(normals, selected, mapping, axis):
    result = list(normals)
    for i in sorted(selected):
        if i in mapping:
            n = list(normals[i])
            n[axis] *= -1
            result[mapping[i]] = tuple(n)
    return result


def paste(mesh, selected, source):
    if not source:
        raise ValueError('Store an active vertex or corner first')
    result = list(mesh.normals)
    for i in set(selected).difference(source):
        j = max(source, key=lambda j: dot(mesh.tangents[i], mesh.tangents[j]))
        result[i] = mesh.normals[j]
    return result
