"""Host-independent normal overlay geometry and session-only visibility.

Separate from Qt and Maya so corner identity, masks, and drawing geometry can
be regression-tested without a GPU. Input mesh positions/normals share a space.
"""
import colorsys
from . import core

def rgba(h,s,v,a=1):
    return colorsys.hsv_to_rgb(h,s,v)+(a,)


PALETTE = {'normal': rgba(.83,.30,.40), 'selected': rgba(.83,.70,.90),
           'active': rgba(0,0,.90)}
POINT_PALETTE = {'normal': rgba(.1,.4,.1), 'selected': rgba(.1,.7,.9),
                 'active': rgba(0,0,.75)}
TRI_PALETTE = {'normal': rgba(.16,.55,.7,.2), 'selected': rgba(.16,.7,.9,.5),
               'active': rgba(0,0,1,.75)}


class Visibility:
    def __init__(self, count):
        self.count = count
        self.hidden = set()
        self._history = [set()]
        self._position = 0

    def _set(self, hidden):
        hidden = set(hidden)
        if hidden == self.hidden:
            return
        self.hidden = hidden
        self._history = self._history[:self._position+1] + [set(hidden)]
        # Bound session display history like the source modal history.
        self._history = self._history[-128:]
        self._position = len(self._history)-1

    def hide(self, selected, unselected=False):
        selected = set(selected)
        if not selected.issubset(range(self.count)):
            raise ValueError('Invalid corner visibility selection')
        hide = set(range(self.count))-selected if unselected else selected
        self._set(self.hidden | hide)

    def reveal(self):
        self._set(set())

    def undo(self):
        self._position = max(0, self._position-1)
        self.hidden = set(self._history[self._position])

    def redo(self):
        self._position = min(len(self._history)-1, self._position+1)
        self.hidden = set(self._history[self._position])


def batches(mesh, selected=(), active=(), hidden=(), weights=None, size=.4,
            selected_only=False, scale_selected=True, draw_weights=False,
            wedges=False, wedge_scale=.18, points=True):
    """Return colored primitive batches, retaining one record per corner.

    Weights are quantized into 16 display bins only; edit weights are untouched.
    Hidden here means hidden from this editor, never hidden Maya geometry.
    """
    selected, active, hidden = set(selected), set(active), set(hidden)
    output = {}
    for i, normal in enumerate(mesh.normals):
        if i in hidden or (selected_only and i not in selected):
            continue
        state = 'active' if i in active else 'selected' if i in selected else 'normal'
        color = PALETTE[state]
        point_color = POINT_PALETTE[state]
        tri_color = TRI_PALETTE[state]
        if draw_weights and weights is not None and weights.get(i,0) > 0:
            weight = round(max(0, min(1, weights.get(i,0))) * 15) / 15
            color = rgba(.66*(1-weight),1,1)
            point_color = tri_color = color
        vertex = mesh.corner_vertices[i]
        face = mesh.corner_faces[i]
        origin = mesh.points[vertex]
        factor = (1 if i in active else .666 if i in selected else .333) if scale_selected else 1
        length = size * factor
        end = core.add(origin, core.mul(core.unit(normal), length))
        output.setdefault(('lines',color), []).extend((origin,end))
        if points:
            output.setdefault(('points',point_color), []).append(origin)
        if wedges:
            vertices = mesh.faces[face]
            local = mesh.face_corners[face].index(i)
            previous = mesh.points[vertices[local-1]]
            following = mesh.points[vertices[(local+1) % len(vertices)]]
            offset = core.mul(mesh.face_normals[face], size*.02)
            triangle = [core.add(origin,offset),
                        core.add(core.add(origin,core.mul(core.sub(following,origin),wedge_scale)),offset),
                        core.add(core.add(origin,core.mul(core.sub(previous,origin),wedge_scale)),offset)]
            output.setdefault(('triangles',tri_color), []).extend(triangle)
    return tuple((kind,color,tuple(vertices)) for (kind,color),vertices in output.items())
