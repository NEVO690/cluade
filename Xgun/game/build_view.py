"""Renders build pieces and the placement ghost."""
from __future__ import annotations

import numpy as np
from panda3d.core import NodePath, SamplerState, TransparencyAttrib

from config import paths
from game import building as B
from world.world_view import build_mesh

TEXTURES = {"wood": "house_b_floor.png", "stone": "house_b_brick.png", "metal": "wh_metal.png"}


def _box_geom(name, boxes):
    """One mesh from several (center, size) boxes, with world-scaled UVs for tiling."""
    verts, norms, uvs, tris = [], [], [], []
    faces = [((1, 0, 0), (0, 1, 2)), ((-1, 0, 0), (0, 1, 2)), ((0, 1, 0), (0, 0, 2)), ((0, -1, 0), (0, 0, 2)),
             ((0, 0, 1), (0, 0, 1)), ((0, 0, -1), (0, 0, 1))]
    for (cx, cy, cz), (sx, sy, sz) in boxes:
        half = np.array([sx, sy, sz]) / 2
        c = np.array([cx, cy, cz])
        for n, _ in faces:
            n = np.array(n, float)
            axis = int(np.argmax(np.abs(n)))
            u_axis, v_axis = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]
            base = len(verts)
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = c + n * half
                p[u_axis] += du * half[u_axis]
                p[v_axis] += dv * half[v_axis]
                verts.append(p)
                norms.append(n)
                uvs.append((p[u_axis] / 2.0, p[v_axis] / 2.0))
            a, b, cc, d = base, base + 1, base + 2, base + 3
            # wind counter-clockwise when seen from outside
            flip = (np.cross(np.eye(3)[u_axis], np.eye(3)[v_axis]) @ n) < 0
            tris += [(a, cc, b), (a, d, cc)] if flip else [(a, b, cc), (a, cc, d)]
    v = np.array(verts)
    return build_mesh(name, v, np.array(norms), np.array(uvs), np.ones((len(v), 4)), np.array(tris))


def _ramp_geom(name, ix, iy, z, direction):
    """Smooth wedge for ramps (collision stays as walkable steps)."""
    cx, cy = B.cell_center(ix, iy)
    dx, dy = B.DIRS[direction]
    px, py = -dy, dx                         # sideways axis
    g, h = B.GRID / 2, B.PIECE_HEIGHT

    def P(a, s, up):                         # a: along slope -1..1, s: side -1..1
        return (cx + dx * a * g + px * s * g, cy + dy * a * g + py * s * g, z + up)
    low_l, low_r = P(-1, -1, 0), P(-1, 1, 0)
    high_l, high_r = P(1, -1, h), P(1, 1, h)
    base_l, base_r = P(1, -1, 0), P(1, 1, 0)
    quads = [((low_l, low_r, high_r, high_l), (0, 0, 2, 2.8)),      # slope
             ((base_l, base_r, high_r, high_l), None),              # back face
             ((low_l, base_l, base_r, low_r), None)]                # underside
    tris_side = [(low_l, base_l, high_l), (low_r, high_r, base_r)]
    verts, norms, uvs, tris = [], [], [], []

    def add(poly):
        pts = [np.array(q, float) for q in poly]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        n /= np.linalg.norm(n) or 1
        base = len(verts)
        for i, q in enumerate(pts):
            verts.append(q)
            norms.append(n)
            uvs.append(((q[0] + q[1]) / 2.0, q[2] / 2.0 + (i % 2) * 0.0))
        for k in range(1, len(pts) - 1):
            tris.append((base, base + k, base + k + 1))
    for poly, _ in quads:
        add(poly)
    for t in tris_side:
        add(t)
    v = np.array(verts)
    node = build_mesh(name, v, np.array(norms), np.array(uvs), np.ones((len(v), 4)), np.array(tris))
    return node


class BuildView:
    def __init__(self, app, parent: NodePath):
        self.app = app
        self.root = parent.attachNewNode("builds")
        self.nodes: dict[int, NodePath] = {}
        self.textures = {}
        for mat, fname in TEXTURES.items():
            tex = app.assets.texture(paths.TEXTURES / "generated" / fname)
            if tex is not None:
                tex.setWrapU(SamplerState.WM_repeat)
                tex.setWrapV(SamplerState.WM_repeat)
            self.textures[mat] = tex
        self.ghost = None
        self.ghost_key = None

    def sync(self, builds: dict) -> None:
        for pid in [p for p in self.nodes if p not in builds]:
            self.nodes.pop(pid).removeNode()
        for pid, piece in builds.items():
            node = self.nodes.get(pid)
            if node is None:
                if piece.kind == "ramp":
                    geom = _ramp_geom(f"piece{pid}", piece.ix, piece.iy, piece.z, piece.direction)
                else:
                    geom = _box_geom(f"piece{pid}", B.piece_boxes(piece.kind, piece.ix, piece.iy, piece.z, piece.direction))
                node = self.root.attachNewNode(geom)
                node.setTwoSided(True)
                tex = self.textures.get(piece.material)
                if tex is not None:
                    node.setTexture(tex, 1)
                self.nodes[pid] = node
            frac = max(0.0, piece.hp / piece.max_hp)
            k = 0.55 + 0.45 * frac             # darker and redder as it breaks
            node.setColorScale(k + (1 - frac) * 0.3, k, k, 1)

    def show_ghost(self, kind: str | None, spot, valid: bool) -> None:
        key = (kind, spot)
        if kind is None or spot is None:
            if self.ghost is not None:
                self.ghost.hide()
            return
        if key != self.ghost_key:
            if self.ghost is not None:
                self.ghost.removeNode()
            ix, iy, z, d = spot
            geom = _ramp_geom("ghost", ix, iy, z, d) if kind == "ramp" else _box_geom("ghost", B.piece_boxes(kind, ix, iy, z, d))
            self.ghost = self.root.attachNewNode(geom)
            self.ghost.setTwoSided(True)
            self.ghost.setTransparency(TransparencyAttrib.M_alpha)
            self.ghost.setDepthWrite(False)
            self.ghost.setLightOff(1)
            self.ghost.setShaderOff(20)
            self.ghost.setBin("transparent", 40)
            self.ghost_key = key
        self.ghost.show()
        self.ghost.setColor((0.3, 0.7, 1.0, 0.35) if valid else (1.0, 0.3, 0.3, 0.35), 2)

    def destroy(self):
        self.root.removeNode()
