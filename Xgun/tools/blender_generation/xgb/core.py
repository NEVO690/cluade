"""Core helpers for procedurally authoring Xgun assets with Blender's Python API.

Conventions (shared with the game):
* Metres, Z up. Characters and weapons face **+Y**; a character's right is **+X**.
* glTF export converts to Y-up and panda3d-gltf converts back, so Blender
  coordinates equal Panda3D coordinates.
* Attachment points are empties named ``socket_*`` (rigid assets) or bones
  named ``socket_*`` (characters).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import bpy  # must precede bmesh/mathutils when running as the bpy module
import bmesh
from mathutils import Euler, Matrix, Vector

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "assets"
TEX_DIR = ASSETS / "textures"
MODEL_DIR = ASSETS / "models"
BLEND_DIR = ASSETS / "blender"


# --------------------------------------------------------------------------
# scene management
# --------------------------------------------------------------------------
def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.render.fps = 30
    _MAT_CACHE.clear()


def link(obj: bpy.types.Object, collection: bpy.types.Collection | None = None) -> bpy.types.Object:
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------
_MAT_CACHE: dict[str, bpy.types.Material] = {}


def hex_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    srgb = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    # Blender colour sockets are linear
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


def material(name: str, color, *, metal: float = 0.0, rough: float = 0.6, emit: float = 0.0,
             emit_color=None, texture: str | None = None, tex_scale: float = 1.0, alpha: float = 1.0):
    """Create (or reuse) a Principled material.

    ``color`` may be '#RRGGBB' or a linear RGB tuple. ``texture`` names a
    procedural detail pattern from :mod:`xgb.textures`; it is baked together
    with the colour into a PNG so the glTF export carries it.
    """
    if name in _MAT_CACHE:
        return _MAT_CACHE[name]
    rgb = hex_rgb(color) if isinstance(color, str) else tuple(color)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if emit > 0:
        ec = emit_color if emit_color is not None else rgb
        ec = hex_rgb(ec) if isinstance(ec, str) else ec
        bsdf.inputs["Emission Color"].default_value = (*ec, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emit
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.surface_render_method = "BLENDED"
    if texture:
        from xgb import textures
        img_path = textures.baked(texture, rgb, name)
        img = bpy.data.images.load(str(img_path), check_existing=True)
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = img
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat["tex_scale"] = tex_scale
    _MAT_CACHE[name] = mat
    return mat


# --------------------------------------------------------------------------
# mesh construction (bmesh based: no operator context needed)
# --------------------------------------------------------------------------
def _new_obj(name: str, bm: bmesh.types.BMesh, mat=None) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    if mat is not None:
        mesh.materials.append(mat)
    link(obj)
    return obj


def _place(obj, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    obj.location = Vector(loc)
    obj.rotation_euler = Euler([math.radians(a) for a in rot], "XYZ")
    obj.scale = Vector(scale) if not isinstance(scale, (int, float)) else Vector((scale,) * 3)
    return obj


def box(name, size, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, bevel: float = 0.0, segments: int = 2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = _place(_new_obj(name, bm, mat), loc, rot)
    if bevel > 0:
        add_bevel(obj, bevel, segments)
    return obj


def cylinder(name, radius, depth, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, verts: int = 16,
             radius_top: float | None = None, bevel: float = 0.0, segments: int = 2, cap: bool = True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=verts, radius1=radius,
                          radius2=radius if radius_top is None else radius_top, depth=depth, calc_uvs=True)
    obj = _place(_new_obj(name, bm, mat), loc, rot)
    if bevel > 0:
        add_bevel(obj, bevel, segments)
    smooth(obj, 40)
    return obj


def sphere(name, radius, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), mat=None, segments=20, rings=12):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius, calc_uvs=True)
    obj = _place(_new_obj(name, bm, mat), loc, rot, scale)
    smooth(obj, 180)
    return obj


def torus(name, major, minor, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, seg=24, ring=10, arc: float = 360.0,
          scale=(1, 1, 1)):
    bm = bmesh.new()
    closed = arc >= 359.9
    n_major = seg if closed else seg + 1
    rows = []
    for i in range(n_major):
        a = math.radians(arc) * i / seg
        center = Vector((math.cos(a) * major, math.sin(a) * major, 0))
        row = []
        for j in range(ring):
            b = 2 * math.pi * j / ring
            offset = Vector((math.cos(a) * math.cos(b), math.sin(a) * math.cos(b), math.sin(b))) * minor
            row.append(bm.verts.new(center + offset))
        rows.append(row)
    for i in range(seg if closed else seg):
        r0, r1 = rows[i], rows[(i + 1) % n_major]
        for j in range(ring):
            bm.faces.new((r0[j], r1[j], r1[(j + 1) % ring], r0[(j + 1) % ring]))
    if not closed:
        bm.faces.new(list(reversed(rows[0])))
        bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _place(_new_obj(name, bm, mat), loc, rot, scale)
    smooth(obj, 180)
    return obj


def prism(name, profile, depth, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, bevel: float = 0.0, axis: str = "X"):
    """Extrude a 2D polygon ``profile`` [(u, v), ...] by ``depth`` (centred).

    axis 'X': profile lies in the YZ plane (u→Y, v→Z) and is extruded along X —
    ideal for side-view silhouettes of weapons, blades and furniture.
    axis 'Z': profile in XY, extruded along Z. axis 'Y': profile in XZ."""
    bm = bmesh.new()
    def to3(u, v, w):
        return {"X": (w, u, v), "Y": (u, w, v), "Z": (u, v, w)}[axis]
    front = [bm.verts.new(to3(u, v, -depth / 2)) for u, v in profile]
    back = [bm.verts.new(to3(u, v, depth / 2)) for u, v in profile]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    n = len(profile)
    for i in range(n):
        bm.faces.new((front[i], front[(i + 1) % n], back[(i + 1) % n], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _place(_new_obj(name, bm, mat), loc, rot)
    if bevel > 0:
        add_bevel(obj, bevel, 2)
    return obj


def lathe(name, profile, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, seg: int = 20):
    """Revolve [(radius, z), ...] around Z (bottles, cans, rounded handles)."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            ring.append(bm.verts.new((math.cos(a) * max(r, 1e-4), math.sin(a) * max(r, 1e-4), z)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        for i in range(seg):
            bm.faces.new((rings[k][i], rings[k][(i + 1) % seg], rings[k + 1][(i + 1) % seg], rings[k + 1][i]))
    if profile[0][0] > 1e-3:
        bm.faces.new(list(reversed(rings[0])))
    if profile[-1][0] > 1e-3:
        bm.faces.new(rings[-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _place(_new_obj(name, bm, mat), loc, rot)
    smooth(obj, 50)
    return obj


def tube(name, points, radius, mat=None, seg: int = 10, radii=None):
    """Sweep a circle along a polyline (cables, straps, bent handles)."""
    bm = bmesh.new()
    pts = [Vector(p) for p in points]
    rings = []
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
        a = d.cross(up).normalized()
        b = d.cross(a).normalized()
        r = radii[i] if radii else radius
        rings.append([bm.verts.new(p + (a * math.cos(t) + b * math.sin(t)) * r)
                      for t in (2 * math.pi * k / seg for k in range(seg))])
    for k in range(len(rings) - 1):
        for i in range(seg):
            bm.faces.new((rings[k][i], rings[k][(i + 1) % seg], rings[k + 1][(i + 1) % seg], rings[k + 1][i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _new_obj(name, bm, mat)
    smooth(obj, 60)
    return obj


def skin_mesh(name, verts, edges, radii, mat=None, subdiv: int = 1, root: int = 0):
    """Organic tube network via the Skin modifier (bodies, sleeves, trousers)."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], edges, [])
    obj = bpy.data.objects.new(name, mesh)
    link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    obj.modifiers.new("skin", "SKIN")
    for i, sv in enumerate(mesh.skin_vertices[0].data):
        r = radii[i]
        sv.radius = r if isinstance(r, (tuple, list)) else (r, r)
        sv.use_root = i == root
    if subdiv:
        sub = obj.modifiers.new("subd", "SUBSURF")
        sub.levels = subdiv
        sub.render_levels = subdiv
    apply_modifiers(obj)
    smooth(obj, 180)
    return obj


# --------------------------------------------------------------------------
# modifiers / shading
# --------------------------------------------------------------------------
def add_bevel(obj, width: float, segments: int = 2, angle: float = 35.0):
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    mod.harden_normals = False
    return mod


def apply_modifiers(obj) -> None:
    if not obj.modifiers:
        return
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True,
                                               depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def smooth(obj, angle_deg: float = 35.0) -> None:
    mesh = obj.data
    for poly in mesh.polygons:
        poly.use_smooth = True
    if angle_deg < 180:
        mesh.set_sharp_from_angle(angle=math.radians(angle_deg))


def subdivide(obj, levels: int = 1):
    mod = obj.modifiers.new("subd", "SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    return mod


def mirror_x(obj):
    mod = obj.modifiers.new("mirror", "MIRROR")
    mod.use_axis[0] = True
    return mod


def box_uv(obj, scale: float = 1.0) -> None:
    """Triplanar box projection in object space — good enough for tiling detail maps."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.verify()
    sx, sy, sz = obj.scale
    for face in bm.faces:
        n = face.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            co = loop.vert.co
            p = (co.x * sx, co.y * sy, co.z * sz)
            if ax == 0:
                u, v = p[1], p[2]
            elif ax == 1:
                u, v = p[0], p[2]
            else:
                u, v = p[0], p[1]
            loop[uv].uv = (u * scale, v * scale)
    bm.to_mesh(obj.data)
    bm.free()


def bake_part(o, *, uv_scale: float = 1.0, keep_uvs: bool = False):
    """Apply modifiers and object transform into the mesh data; add box UVs."""
    apply_modifiers(o)
    mat = o.matrix_world.copy()
    o.parent = None
    o.data.transform(mat)
    if mat.determinant() < 0:
        o.data.flip_normals()
    o.matrix_world = Matrix.Identity(4)
    if not keep_uvs or not o.data.uv_layers:
        scale = uv_scale
        if o.data.materials and o.data.materials[0] is not None:
            scale *= float(o.data.materials[0].get("tex_scale", 1.0))
        box_uv(o, scale)
    return o


def join(objects, name: str):
    objects = [o for o in objects if o is not None]
    target = objects[0]
    if len(objects) > 1:
        with bpy.context.temp_override(active_object=target, selected_editable_objects=objects,
                                       selected_objects=objects):
            bpy.ops.object.join()
    target.name = name
    target.data.name = name
    return target


def finalize(objects, name: str, *, uv_scale: float = 1.0, keep_uvs: bool = False):
    """Apply transforms/modifiers, give everything UVs, and join into one mesh."""
    objects = [o for o in objects if o is not None]
    bpy.context.view_layer.update()  # matrix_world is stale until the depsgraph runs
    for o in objects:
        bake_part(o, uv_scale=uv_scale, keep_uvs=keep_uvs)
    return join(objects, name)


def socket(name: str, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
    empty = bpy.data.objects.new(name if name.startswith("socket_") else "socket_" + name, None)
    empty.empty_display_type = "ARROWS"
    empty.empty_display_size = 0.08
    link(empty)
    _place(empty, loc, rot)
    if parent is not None:
        empty.parent = parent
    return empty


def triangle_count(obj) -> int:
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
def export(category: str, asset_id: str, objects, *, animations: bool = False) -> dict:
    model_path = MODEL_DIR / category / f"{asset_id}.glb"
    blend_path = BLEND_DIR / category / f"{asset_id}.blend"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
        for child in o.children_recursive:
            child.select_set(True)
    kwargs = dict(filepath=str(model_path), export_format="GLB", use_selection=True, export_apply=False,
                  export_yup=True, export_texcoords=True, export_normals=True, export_materials="EXPORT",
                  export_extras=True, export_animations=animations, export_skins=True)
    if animations:
        kwargs.update(export_animation_mode="ACTIONS", export_force_sampling=True, export_frame_step=1,
                      export_anim_single_armature=True, export_reset_pose_bones=True,
                      export_optimize_animation_size=True)
    bpy.ops.export_scene.gltf(**kwargs)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True, relative_remap=True)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.select_get()]
    tris = sum(triangle_count(o) for o in meshes)
    rel = model_path.relative_to(MODEL_DIR).as_posix()
    return {"model": rel, "blend": blend_path.relative_to(ROOT).as_posix(), "triangles": tris,
            "bytes": os.path.getsize(model_path)}


def bounds(objects) -> dict:
    pts = [o.matrix_world @ Vector(c) for o in objects if o.type == "MESH" for c in o.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}


def update_manifest(entries: dict) -> None:
    path = MODEL_DIR / "manifest.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(entries)
    path.write_text(json.dumps(dict(sorted(data.items())), indent=1))
