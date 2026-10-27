"""Mesh-building helpers for the BONK! Blender scripts (bmesh based, no UI operators).

Works both inside the Blender application (blender -b -P ...) and with the
`bpy` Python module from PyPI.
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 24
    return scene


def material(name, color, roughness=0.5, metallic=0.0, emission=None, emission_strength=0.0):
    """Principled BSDF material; colour is an sRGB hex string like '#ff8800'."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    rgba = hex_to_linear(color)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = hex_to_linear(emission)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = rgba
    # Closed meshes: export single-sided (glTF doubleSided=false).  Double-sided
    # materials make the game's shadow map self-shadow ("shadow acne").
    mat.use_backface_culling = True
    return mat


def hex_to_linear(h):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (lin(srgb[0]), lin(srgb[1]), lin(srgb[2]), 1.0)


class MeshBuilder:
    """Accumulates primitives into one bmesh with per-vertex bone weights."""

    def __init__(self, groups=()):
        self.bm = bmesh.new()
        self.deform = self.bm.verts.layers.deform.verify()
        self.groups = list(groups)

    def _gi(self, name):
        if name not in self.groups:
            self.groups.append(name)
        return self.groups.index(name)

    def _finish(self, verts, xform, weights):
        for v in verts:
            v.co = xform @ v.co
        for v in verts:
            w = weights(v.co) if callable(weights) else weights
            for bone, val in (w or {}).items():
                if val > 1e-4:
                    v[self.deform][self._gi(bone)] = val
        return verts

    def sphere(self, center, radii, weights, segs=24, rings=14, rot=None, taper=None):
        ret = bmesh.ops.create_uvsphere(self.bm, u_segments=segs, v_segments=rings, radius=1.0)
        verts = ret["verts"]
        for v in verts:
            x, y, z = v.co.x * radii[0], v.co.y * radii[1], v.co.z * radii[2]
            if taper is not None:
                k = taper(v.co.z)
                x, y = x * k, y * k
            v.co = Vector((x, y, z))
        m = Matrix.Translation(Vector(center))
        if rot is not None:
            m = m @ rot.to_matrix().to_4x4()
        return self._finish(verts, m, weights)

    def cylinder(self, p0, p1, r0, r1, weights, segs=16, caps=True):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        length = d.length
        ret = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=segs,
                                    radius1=r0, radius2=r1, depth=length)
        verts = ret["verts"]
        # create_cone is centred on the origin along +Z.
        rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
        m = Matrix.Translation((p0 + p1) * 0.5) @ rot
        return self._finish(verts, m, weights)

    def box(self, center, size, weights, bevel=0.0):
        ret = bmesh.ops.create_cube(self.bm, size=1.0)
        verts = ret["verts"]
        for v in verts:
            v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
        self._finish(verts, Matrix.Translation(Vector(center)), weights)
        if bevel > 0:
            edges = list({e for v in verts for e in v.link_edges})
            bmesh.ops.bevel(self.bm, geom=verts + edges, offset=bevel, segments=2, affect="EDGES")
        return verts

    def torus(self, center, major, minor, weights, segs=32, rings=10, rot=None):
        verts = []
        rows = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            row = []
            for j in range(rings):
                b = 2 * math.pi * j / rings
                r = major + minor * math.cos(b)
                row.append(self.bm.verts.new((r * math.cos(a), r * math.sin(a), minor * math.sin(b))))
            rows.append(row)
            verts += row
        for i in range(segs):
            for j in range(rings):
                a, b = rows[i][j], rows[(i + 1) % segs][j]
                c, d = rows[(i + 1) % segs][(j + 1) % rings], rows[i][(j + 1) % rings]
                self.bm.faces.new((a, b, c, d))
        m = Matrix.Translation(Vector(center))
        if rot is not None:
            m = m @ rot.to_matrix().to_4x4()
        return self._finish(verts, m, weights)

    def cone(self, p0, p1, r0, weights, segs=16):
        return self.cylinder(p0, p1, r0, 0.0005, weights, segs)

    def to_object(self, name, mat, smooth=True, parent=None):
        mesh = bpy.data.meshes.new(name)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[:])
        self.bm.to_mesh(mesh)
        self.bm.free()
        if smooth:
            mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        for g in self.groups:
            obj.vertex_groups.new(name=g)
        if parent is not None:
            obj.parent = parent
            mod = obj.modifiers.new("Armature", "ARMATURE")
            mod.object = parent
        return obj


def smoothstep(a, b, x):
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    t = (x - a) / (b - a)
    return t * t * (3 - 2 * t)


def export_glb(path, objects, animations=False):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_skins=True,
        export_animations=animations,
        export_animation_mode="ACTIONS",
        export_yup=True,
        export_materials="EXPORT",
    )
