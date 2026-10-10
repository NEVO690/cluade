"""Renders the island: chunked terrain, water, sky, roads and static scenery."""
from __future__ import annotations

import math

import numpy as np
from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat,
                          NodePath, SamplerState, Texture, TextureStage, TransparencyAttrib, Vec4)

from config import paths
from world.island import IslandLayout
from world.terrain import CELL, HALF_EXTENT

CHUNKS = 8
DYNAMIC = {"env_loot_chest", "env_loot_chest_lid", "env_supply_crate", "env_ammo_box"}


def _format() -> GeomVertexFormat:
    arr = GeomVertexArrayFormat()
    arr.addColumn("vertex", 3, Geom.NT_float32, Geom.C_point)
    arr.addColumn("normal", 3, Geom.NT_float32, Geom.C_normal)
    arr.addColumn("texcoord", 2, Geom.NT_float32, Geom.C_texcoord)
    arr.addColumn("color", 4, Geom.NT_float32, Geom.C_color)
    return GeomVertexFormat.registerFormat(GeomVertexFormat(arr))


def build_mesh(name, verts, normals, uvs, colors, tris) -> GeomNode:
    fmt = _format()
    vdata = GeomVertexData(name, fmt, Geom.UH_static)
    data = np.hstack([verts, normals, uvs, colors]).astype(np.float32)
    vdata.unclean_set_num_rows(len(data))
    view = memoryview(vdata.modify_array(0)).cast("B").cast("f")
    view[:] = data.ravel()
    prim = GeomTriangles(Geom.UH_static)
    prim.setIndexType(Geom.NT_uint32)
    idx = prim.modify_vertices()
    idx.unclean_set_num_rows(len(tris) * 3)
    memoryview(idx).cast("B").cast("I")[:] = tris.astype(np.uint32).ravel()
    geom = Geom(vdata)
    geom.addPrimitive(prim)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


class WorldView:
    def __init__(self, app, layout: IslandLayout, quality: str = "High"):
        self.app = app
        self.layout = layout
        self.root = app.render.attachNewNode("world")
        self.quality = quality
        self.static_root = self.root.attachNewNode("static")
        self.chunks: list[tuple[NodePath, float, float]] = []

    def build(self):
        """Generator so a loading screen can show progress between steps."""
        yield "Shaping terrain", self._terrain()
        yield "Filling the ocean", self._water()
        yield "Painting the sky", self._sky()
        yield "Paving roads", self._roads()
        yield "Raising buildings", self._scenery()

    # ----------------------------------------------------------- terrain
    def _terrain(self):
        t = self.layout.terrain
        h = t.h
        n = t.size
        xs = t.xs
        gy, gx = np.gradient(h, CELL)
        nz = np.ones_like(h) * 1.0
        normals = np.stack([-gx, -gy, nz], -1)
        normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
        slope = 1 - normals[..., 2]
        # vertex colour = splat weights (r=grass g=sand b=rock a=road)
        sand = np.clip((4.0 - h) / 3.0, 0, 1)
        rock = np.clip((slope - 0.18) * 6, 0, 1) * (1 - sand)
        grass = np.clip(1 - sand - rock, 0, 1)
        road = np.zeros_like(h)
        from world.island import _dist_to_polyline
        X, Y = np.meshgrid(xs, xs)
        for r in self.layout.roads:
            for (x0, y0), (x1, y1) in zip(r, r[1:]):
                dx, dy = x1 - x0, y1 - y0
                l2 = dx * dx + dy * dy or 1
                tt = np.clip(((X - x0) * dx + (Y - y0) * dy) / l2, 0, 1)
                d = np.hypot(X - (x0 + dx * tt), Y - (y0 + dy * tt))
                road = np.maximum(road, np.clip((5.5 - d) / 2.0, 0, 1))
        for p in self.layout.pois:   # paved plazas
            d = np.hypot(X - p.x, Y - p.y)
            road = np.maximum(road, np.clip((p.radius * 0.35 - d) / 6.0, 0, 1) * 0.85)
        colors = np.stack([grass, sand, rock, road], -1)
        tex_scale = 1 / 8.0
        per = (n - 1) // CHUNKS
        for cy in range(CHUNKS):
            for cx in range(CHUNKS):
                i0, j0 = cy * per, cx * per
                i1, j1 = min(n - 1, i0 + per), min(n - 1, j0 + per)
                sub_h = h[i0:i1 + 1, j0:j1 + 1]
                if sub_h.max() < -4.5:
                    continue  # deep ocean: water plane only
                rows, cols = sub_h.shape
                vx, vy = np.meshgrid(xs[j0:j1 + 1], xs[i0:i1 + 1])
                verts = np.stack([vx, vy, sub_h], -1).reshape(-1, 3)
                nrm = normals[i0:i1 + 1, j0:j1 + 1].reshape(-1, 3)
                uv = np.stack([vx * tex_scale, vy * tex_scale], -1).reshape(-1, 2)
                col = colors[i0:i1 + 1, j0:j1 + 1].reshape(-1, 4)
                r, c = np.meshgrid(np.arange(rows - 1), np.arange(cols - 1), indexing="ij")
                a = (r * cols + c).ravel()
                b, cc, d = a + 1, a + cols, a + cols + 1
                tris = np.stack([np.stack([a, b, d], -1), np.stack([a, d, cc], -1)], 1).reshape(-1, 3)
                node = build_mesh(f"terrain_{cx}_{cy}", verts, nrm, uv, col, tris)
                np_ = self.root.attachNewNode(node)
                self.chunks.append((np_, float(vx.mean()), float(vy.mean())))
        self._terrain_shader()

    def _terrain_shader(self):
        """Texture splatting by vertex colour (falls back to plain vertex colours without shaders)."""
        from panda3d.core import Shader
        tex = {}
        for k in ("grass", "sand", "rock", "road"):
            t = self.app.assets.texture(paths.TEXTURES / "terrain" / f"{k}.png")
            if t is not None:
                t.setWrapU(SamplerState.WM_repeat)
                t.setWrapV(SamplerState.WM_repeat)
            tex[k] = t
        terrain_nodes = [c[0] for c in self.chunks]
        if not self.app.shaders_ok or any(v is None for v in tex.values()):
            for np_ in terrain_nodes:
                np_.setColorScale(0.6, 0.75, 0.5, 1)
            return
        shader = Shader.make(Shader.SL_GLSL, TERRAIN_VERT, TERRAIN_FRAG)
        for np_ in terrain_nodes:
            np_.setShader(shader, 10)
            for k, t in tex.items():
                np_.setShaderInput(f"t_{k}", t)
        self.terrain_nodes = terrain_nodes

    # ------------------------------------------------------------- water
    def _water(self):
        from panda3d.core import CardMaker
        cm = CardMaker("water")
        cm.setFrame(-3000, 3000, -3000, 3000)
        water = self.root.attachNewNode(cm.generate())
        water.setP(-90)
        water.setZ(0.0)
        water.setColor(0.12, 0.42, 0.62, 0.82)
        water.setTransparency(TransparencyAttrib.M_alpha)
        water.setBin("transparent", 0)
        water.setDepthWrite(False)
        self.water = water
        if self.app.shaders_ok:
            from panda3d.core import Shader
            water.setShader(Shader.make(Shader.SL_GLSL, WATER_VERT, WATER_FRAG), 10)
            water.setShaderInput("time", 0.0)

    def _sky(self):
        # gradient sky dome from a lathed hemisphere with vertex colours
        rings, seg = 16, 32
        verts, cols, tris = [], [], []
        for i in range(rings + 1):
            el = math.radians(-10 + 100 * i / rings)
            for j in range(seg + 1):
                az = 2 * math.pi * j / seg
                verts.append((math.cos(el) * math.cos(az) * 2500, math.cos(el) * math.sin(az) * 2500, math.sin(el) * 2500))
                t = max(0.0, min(1.0, (math.degrees(el) + 10) / 70))
                horizon = np.array([0.95, 0.78, 0.62])
                zen = np.array([0.18, 0.42, 0.85])
                c = horizon * (1 - t) + zen * t
                cols.append((*c, 1.0))
        for i in range(rings):
            for j in range(seg):
                a = i * (seg + 1) + j
                tris += [(a, a + seg + 1, a + 1), (a + 1, a + seg + 1, a + seg + 2)]
        v = np.array(verts)
        node = build_mesh("sky", v, -v / 2500, np.zeros((len(v), 2)), np.array(cols), np.array(tris))
        sky = self.app.render.attachNewNode(node)
        sky.setLightOff(1)
        sky.setShaderOff(20)
        sky.setBin("background", 0)
        sky.setDepthWrite(False)
        sky.setCompass()
        sky.setTwoSided(True)
        sky.reparentTo(self.app.camera)
        sky.setCompass()
        sky.setFogOff(1)
        self.sky = sky
        # cloud cards
        from panda3d.core import CardMaker
        rng = np.random.default_rng(5)
        self.clouds = self.root.attachNewNode("clouds")
        for i in range(40):
            cm = CardMaker("cloud")
            w = rng.uniform(60, 160)
            cm.setFrame(-w, w, -w * 0.35, w * 0.35)
            c = self.clouds.attachNewNode(cm.generate())
            a = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(150, 900)
            c.setPos(math.cos(a) * d, math.sin(a) * d, rng.uniform(260, 380))
            c.setBillboardPointEye()
            c.setColor(1, 1, 1, rng.uniform(0.35, 0.6))
            c.setTransparency(TransparencyAttrib.M_alpha)
            c.setLightOff(1)
            c.setShaderOff(20)
            c.setDepthWrite(False)
            c.setBin("transparent", 5)
        self.clouds.setTexture(_cloud_texture(), 1)

    def _roads(self):
        pass  # roads are painted into the terrain splat map (see _terrain)

    # ----------------------------------------------------------- scenery
    def _scenery(self):
        assets = self.app.assets
        size = HALF_EXTENT * 2 / CHUNKS
        buckets: dict[tuple[int, int], NodePath] = {}
        for pl in self.layout.placements:
            if pl.asset in DYNAMIC:
                continue
            key = (int((pl.x + HALF_EXTENT) // size), int((pl.y + HALF_EXTENT) // size))
            if key not in buckets:
                buckets[key] = NodePath(f"scenery_{key[0]}_{key[1]}")
            m = assets.model(pl.asset)
            m.reparentTo(buckets[key])
            m.setPos(pl.x, pl.y, pl.z)
            m.setH(pl.heading)
            m.setScale(pl.scale)
        for key, np_ in buckets.items():
            np_.flattenStrong()      # one batch per material per chunk
            np_.reparentTo(self.static_root)
            cx = -HALF_EXTENT + (key[0] + 0.5) * size
            cy = -HALF_EXTENT + (key[1] + 0.5) * size
            self.chunks.append((np_, cx, cy))

    def update(self, cam_pos, view_distance: float, t: float) -> None:
        if hasattr(self, "water") and self.app.shaders_ok:
            self.water.setShaderInput("time", t)
        limit = view_distance + HALF_EXTENT * 2 / CHUNKS
        for np_, cx, cy in self.chunks:
            d = math.hypot(cam_pos[0] - cx, cam_pos[1] - cy)
            if d > limit:
                np_.hide()
            else:
                np_.show()

    def destroy(self):
        self.root.removeNode()
        if hasattr(self, "sky"):
            self.sky.removeNode()


def _cloud_texture() -> Texture:
    size = 128
    y, x = np.mgrid[0:size, 0:size] / (size - 1) * 2 - 1
    rng = np.random.default_rng(3)
    blobs = np.zeros((size, size))
    for _ in range(9):
        cx, cy, r = rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3), rng.uniform(0.25, 0.5)
        blobs = np.maximum(blobs, np.clip(1 - ((x - cx) ** 2 + ((y - cy) * 1.6) ** 2) / r ** 2, 0, 1))
    alpha = (blobs ** 1.5 * 255).astype(np.uint8)
    img = np.dstack([np.full_like(alpha, 255)] * 3 + [alpha])
    tex = Texture("cloud")
    tex.setup2dTexture(size, size, Texture.T_unsigned_byte, Texture.F_rgba8)
    tex.setRamImageAs(img[::-1].tobytes(), "RGBA")
    return tex


TERRAIN_VERT = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat3 p3d_NormalMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec2 p3d_MultiTexCoord0;
in vec4 p3d_Color;
out vec2 uv;
out vec4 splat;
out vec3 n_view;
out vec3 p_view;
out float height;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uv = p3d_MultiTexCoord0;
    splat = p3d_Color;
    n_view = normalize(p3d_NormalMatrix * p3d_Normal);
    p_view = (p3d_ModelViewMatrix * p3d_Vertex).xyz;
    height = p3d_Vertex.z;
}
"""

TERRAIN_FRAG = """
#version 150
uniform sampler2D t_grass;
uniform sampler2D t_sand;
uniform sampler2D t_rock;
uniform sampler2D t_road;
uniform struct p3d_LightSourceParameters {
    vec4 color;
    vec4 position;
} p3d_LightSource[2];
uniform struct { vec4 ambient; } p3d_LightModel;
uniform struct { vec4 color; float density; } p3d_Fog;
in vec2 uv;
in vec4 splat;
in vec3 n_view;
in vec3 p_view;
in float height;
out vec4 frag;
void main() {
    // textures are sRGB; light in linear space (simplepbr tone-maps and encodes the final image)
    vec3 g = pow(texture(t_grass, uv).rgb, vec3(2.2));
    vec3 s = pow(texture(t_sand, uv * 1.3).rgb, vec3(2.2));
    vec3 r = pow(texture(t_rock, uv * 0.7).rgb, vec3(2.2));
    vec3 d = pow(texture(t_road, uv * 0.6).rgb, vec3(2.2));
    float total = splat.r + splat.g + splat.b + 1e-4;
    vec3 base = (g * splat.r + s * splat.g + r * splat.b) / total;
    base = mix(base, d, clamp(splat.a, 0.0, 1.0));
    if (height < 0.0) base = mix(base, vec3(0.55, 0.5, 0.38), clamp(-height / 3.0, 0.0, 1.0));
    vec3 lit = p3d_LightModel.ambient.rgb;
    for (int i = 0; i < 2; ++i) {
        vec3 L = p3d_LightSource[i].position.xyz - p_view * p3d_LightSource[i].position.w;
        lit += p3d_LightSource[i].color.rgb * max(dot(normalize(n_view), normalize(L)), 0.0);
    }
    vec3 color = base * lit;
    float fog = 1.0 - clamp(exp(-length(p_view) * p3d_Fog.density), 0.0, 1.0);
    color = mix(color, p3d_Fog.color.rgb, fog);
    frag = vec4(color, 1.0);
}
"""

WATER_VERT = """
#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
out vec3 world;
out vec3 p_view;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    world = (p3d_ModelMatrix * p3d_Vertex).xyz;
    p_view = (p3d_ModelViewMatrix * p3d_Vertex).xyz;
}
"""

WATER_FRAG = """
#version 150
uniform float time;
uniform struct { vec4 color; float density; } p3d_Fog;
in vec3 world;
in vec3 p_view;
out vec4 frag;
void main() {
    float w = sin(world.x * 0.08 + time * 0.9) * 0.5 + sin(world.y * 0.11 - time * 0.7) * 0.5;
    float w2 = sin((world.x + world.y) * 0.31 + time * 1.7);
    vec3 deep = vec3(0.05, 0.25, 0.42);
    vec3 shallow = vec3(0.16, 0.55, 0.68);
    vec3 c = mix(deep, shallow, 0.5 + 0.25 * w) + vec3(0.12) * smoothstep(0.85, 1.0, w2);
    float fog = 1.0 - clamp(exp(-length(p_view) * p3d_Fog.density), 0.0, 1.0);
    c = mix(c, p3d_Fog.color.rgb, fog);
    frag = vec4(c, 0.86);
}
"""
