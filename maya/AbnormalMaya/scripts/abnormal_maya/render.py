"""Viewport draw submission, isolated for strict signature/cleanup tests.

The caller provides native Maya point arrays/colors and enum constants. No
Maya import here: the 3D/2D argument is mandatory in our test draw manager too.
"""


def draw(manager, batches, xray=False, point_size=4, line_width=1.5,
         nonselectable=0, triangles=0):
    manager.beginDrawable(nonselectable)
    xray_started = False
    try:
        if xray:
            manager.beginDrawInXray()
            xray_started = True
        manager.setLineWidth(line_width)
        manager.setPointSize(point_size)
        for kind,color,vertices in batches:
            manager.setColor(color)
            if kind == 'lines':
                manager.lineList(vertices,False)
            elif kind == 'points':
                manager.points(vertices,False)
            else:
                manager.mesh(triangles,vertices)
    finally:
        try:
            if xray_started:
                manager.endDrawInXray()
        finally:
            manager.endDrawable()
