"""Procedural meshes for course pieces (boxes, cylinders, gradients) built straight
into Panda3D GeomVertexData - no external files needed for platforms."""

import math

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, NodePath)


def hex_color(h, alpha=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, alpha)


def shade(c, k):
    return (min(1.0, c[0] * k), min(1.0, c[1] * k), min(1.0, c[2] * k), c[3])


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


class MeshBuilder:
    """Collects coloured, normal-mapped triangles; `node()` turns them into a GeomNode."""

    def __init__(self, name="mesh"):
        self.name = name
        fmt = GeomVertexFormat.getV3n3c4()
        self.vdata = GeomVertexData(name, fmt, Geom.UHStatic)
        self.vw = GeomVertexWriter(self.vdata, "vertex")
        self.nw = GeomVertexWriter(self.vdata, "normal")
        self.cw = GeomVertexWriter(self.vdata, "color")
        self.tris = GeomTriangles(Geom.UHStatic)
        self.count = 0

    def quad(self, p0, p1, p2, p3, normal, c0, c1=None, c2=None, c3=None):
        c1 = c1 or c0
        c2 = c2 or c1
        c3 = c3 or c0
        base = self.count
        for p, c in ((p0, c0), (p1, c1), (p2, c2), (p3, c3)):
            self.vw.addData3(*p)
            self.nw.addData3(*normal)
            self.cw.addData4(*c)
        self.tris.addVertices(base, base + 1, base + 2)
        self.tris.addVertices(base, base + 2, base + 3)
        self.count += 4

    def tri(self, p0, p1, p2, normal, c):
        base = self.count
        for p in (p0, p1, p2):
            self.vw.addData3(*p)
            self.nw.addData3(*normal)
            self.cw.addData4(*c)
        self.tris.addVertices(base, base + 1, base + 2)
        self.count += 3

    def box(self, minx, miny, minz, maxx, maxy, maxz, top, side=None, bottom=None, pattern=None,
            stripe=None, cell=2.0):
        """Axis-aligned box.  The top can be striped / checkered for readability."""
        side = side or shade(top, 0.78)
        bottom = bottom or shade(top, 0.5)
        if pattern in ("checker", "start", "finish") and (maxx - minx) > 0.5 and (maxy - miny) > 0.5:
            self._checker_top(minx, miny, maxx, maxy, maxz, top, stripe or shade(top, 0.85), cell)
        elif pattern == "stripes" and stripe is not None:
            self._striped_top(minx, miny, maxx, maxy, maxz, top, stripe)
        else:
            self.quad((minx, miny, maxz), (maxx, miny, maxz), (maxx, maxy, maxz), (minx, maxy, maxz),
                      (0, 0, 1), top)
        lo = shade(side, 0.82)
        # Sides get a darker lower edge (cheap ambient occlusion look).
        self.quad((minx, miny, minz), (maxx, miny, minz), (maxx, miny, maxz), (minx, miny, maxz),
                  (0, -1, 0), lo, lo, side, side)
        self.quad((maxx, maxy, minz), (minx, maxy, minz), (minx, maxy, maxz), (maxx, maxy, maxz),
                  (0, 1, 0), lo, lo, side, side)
        self.quad((minx, maxy, minz), (minx, miny, minz), (minx, miny, maxz), (minx, maxy, maxz),
                  (-1, 0, 0), lo, lo, side, side)
        self.quad((maxx, miny, minz), (maxx, maxy, minz), (maxx, maxy, maxz), (maxx, miny, maxz),
                  (1, 0, 0), lo, lo, side, side)
        self.quad((minx, maxy, minz), (maxx, maxy, minz), (maxx, miny, minz), (minx, miny, minz),
                  (0, 0, -1), bottom)
        # Light rim along the top edges.
        rim = shade(top, 1.12)
        e = 0.06
        self.quad((minx, miny, maxz + 0.002), (maxx, miny, maxz + 0.002), (maxx, miny + e, maxz + 0.002),
                  (minx, miny + e, maxz + 0.002), (0, 0, 1), rim)
        self.quad((minx, maxy - e, maxz + 0.002), (maxx, maxy - e, maxz + 0.002), (maxx, maxy, maxz + 0.002),
                  (minx, maxy, maxz + 0.002), (0, 0, 1), rim)

    def _checker_top(self, minx, miny, maxx, maxy, z, a, b, cell):
        nx = max(1, int(round((maxx - minx) / cell)))
        ny = max(1, int(round((maxy - miny) / cell)))
        sx, sy = (maxx - minx) / nx, (maxy - miny) / ny
        for i in range(nx):
            for j in range(ny):
                c = a if (i + j) % 2 == 0 else b
                x0, y0 = minx + i * sx, miny + j * sy
                self.quad((x0, y0, z), (x0 + sx, y0, z), (x0 + sx, y0 + sy, z), (x0, y0 + sy, z), (0, 0, 1), c)

    def _striped_top(self, minx, miny, maxx, maxy, z, a, b, width=0.5):
        n = max(1, int((maxx - minx) / width))
        sx = (maxx - minx) / n
        for i in range(n):
            c = a if i % 2 == 0 else b
            x0 = minx + i * sx
            self.quad((x0, miny, z), (x0 + sx, miny, z), (x0 + sx, maxy, z), (x0, maxy, z), (0, 0, 1), c)

    def wedge(self, minx, miny, maxx, maxy, z0, z1, bottom_z, top, side=None):
        """Ramp rising from z0 at miny to z1 at maxy."""
        side = side or shade(top, 0.78)
        n = (0.0, -(z1 - z0), (maxy - miny))
        l = math.sqrt(n[1] ** 2 + n[2] ** 2) or 1.0
        n = (0.0, n[1] / l, n[2] / l)
        self.quad((minx, miny, z0), (maxx, miny, z0), (maxx, maxy, z1), (minx, maxy, z1), n, top)
        self.quad((minx, miny, bottom_z), (maxx, miny, bottom_z), (maxx, miny, z0), (minx, miny, z0), (0, -1, 0), side)
        self.quad((maxx, maxy, bottom_z), (minx, maxy, bottom_z), (minx, maxy, z1), (maxx, maxy, z1), (0, 1, 0), side)
        self.quad((minx, maxy, bottom_z), (minx, miny, bottom_z), (minx, miny, z0), (minx, maxy, z1), (-1, 0, 0), side)
        self.quad((maxx, miny, bottom_z), (maxx, maxy, bottom_z), (maxx, maxy, z1), (maxx, miny, z0), (1, 0, 0), side)

    def cylinder(self, cx, cy, z0, z1, r, color, segs=20, cap=True, top_color=None):
        top_color = top_color or shade(color, 1.1)
        for i in range(segs):
            a0 = 2 * math.pi * i / segs
            a1 = 2 * math.pi * (i + 1) / segs
            n = (math.cos((a0 + a1) / 2), math.sin((a0 + a1) / 2), 0)
            p0 = (cx + math.cos(a0) * r, cy + math.sin(a0) * r)
            p1 = (cx + math.cos(a1) * r, cy + math.sin(a1) * r)
            self.quad((p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z1), (p0[0], p0[1], z1), n,
                      shade(color, 0.8), shade(color, 0.8), color, color)
            if cap:
                self.tri((cx, cy, z1), (p0[0], p0[1], z1), (p1[0], p1[1], z1), (0, 0, 1), top_color)

    def capsule_bar(self, length, radius, color, stripe=None, segs=12, stripes=6):
        """Bar along +X from 0 to `length` (sweeper arm)."""
        n_st = max(1, stripes)
        seg_len = length / n_st
        for k in range(n_st):
            c = color if (k % 2 == 0 or stripe is None) else stripe
            x0, x1 = k * seg_len, (k + 1) * seg_len
            for i in range(segs):
                a0 = 2 * math.pi * i / segs
                a1 = 2 * math.pi * (i + 1) / segs
                n = (0, math.cos((a0 + a1) / 2), math.sin((a0 + a1) / 2))
                y0, z0 = math.cos(a0) * radius, math.sin(a0) * radius
                y1, z1 = math.cos(a1) * radius, math.sin(a1) * radius
                self.quad((x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1), n, c)
        # end cap
        for i in range(segs):
            a0 = 2 * math.pi * i / segs
            a1 = 2 * math.pi * (i + 1) / segs
            self.tri((length, 0, 0), (length, math.cos(a1) * radius, math.sin(a1) * radius),
                     (length, math.cos(a0) * radius, math.sin(a0) * radius), (1, 0, 0), shade(color, 1.1))

    def node(self):
        geom = Geom(self.vdata)
        geom.addPrimitive(self.tris)
        gn = GeomNode(self.name)
        gn.addGeom(geom)
        return NodePath(gn)


def sky_dome(top, bottom, horizon=None, radius=400.0, segs=32, rings=12):
    """Inverted hemisphere-ish sphere with a vertical colour gradient."""
    horizon = horizon or mix(top, bottom, 0.75)
    mb = MeshBuilder("sky")
    for j in range(rings):
        v0 = -0.35 + 1.35 * j / rings
        v1 = -0.35 + 1.35 * (j + 1) / rings

        def col(v):
            if v < 0.0:
                return bottom
            if v < 0.25:
                return mix(bottom, horizon, v / 0.25)
            return mix(horizon, top, min(1.0, (v - 0.25) / 0.75))

        e0, e1 = math.asin(max(-1, min(1, v0))), math.asin(max(-1, min(1, v1)))
        for i in range(segs):
            a0 = 2 * math.pi * i / segs
            a1 = 2 * math.pi * (i + 1) / segs

            def p(a, e):
                return (math.cos(a) * math.cos(e) * radius, math.sin(a) * math.cos(e) * radius, math.sin(e) * radius)

            mb.quad(p(a0, e0), p(a0, e1), p(a1, e1), p(a1, e0), (0, 0, 1), col(v0), col(v1), col(v1), col(v0))
    return mb.node()
