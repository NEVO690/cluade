"""Cycles preview renders: every asset is lit and rendered before export.

The renders double as the shop / locker thumbnails (transparent PNG)."""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from xgb.core import ASSETS


def render_preview(asset_id: str, objects, *, size: int = 384, yaw: float = 25.0, pitch: float = 12.0,
                   samples: int = 24, pose_armature=None, pose_action: str | None = None, frame: int = 0,
                   margin: float = 1.12) -> str:
    scene = bpy.context.scene
    if pose_armature is not None and pose_action:
        pose_armature.animation_data.action = bpy.data.actions[pose_action]
        scene.frame_set(frame)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objects:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(deps)
        mesh = ev.to_mesh()
        mw = o.matrix_world
        pts += [mw @ v.co for v in list(mesh.vertices)[:: max(1, len(mesh.vertices) // 4000)]]
        ev.to_mesh_clear()
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.05)

    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 70
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    fov = 2 * math.atan(cam_data.sensor_width / (2 * cam_data.lens))
    dist = radius * margin / math.sin(fov / 2)
    yr, pr = math.radians(yaw), math.radians(pitch)
    direction = Vector((math.sin(yr) * math.cos(pr), math.cos(yr) * math.cos(pr), math.sin(pr)))
    cam.location = center + direction * dist
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    lights = []
    for name, energy, loc, color in (("Key", 900, (2.5, 3.0, 4.0), (1.0, 0.95, 0.88)),
                                     ("Fill", 300, (-3.5, 2.0, 1.5), (0.75, 0.85, 1.0)),
                                     ("Rim", 700, (0.5, -4.0, 3.0), (0.9, 0.8, 1.0))):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy * max(radius, 0.3) ** 2
        ld.size = 2.5 * max(radius, 0.3)
        ld.color = color
        lo_obj = bpy.data.objects.new(name, ld)
        lo_obj.location = center + Vector(loc) * max(radius, 0.3) * 1.4
        lo_obj.rotation_euler = (center - lo_obj.location).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(lo_obj)
        lights.append(lo_obj)

    world = scene.world or bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.25, 0.27, 0.32, 1)
    bg.inputs["Strength"].default_value = 0.6

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    scene.render.film_transparent = True
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in
        scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    out = ASSETS / "ui" / "thumbs" / f"{asset_id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)

    for o in lights + [cam]:
        bpy.data.objects.remove(o, do_unlink=True)
    if pose_armature is not None:
        pose_armature.animation_data.action = None
        scene.frame_set(0)
    return str(out.relative_to(ASSETS))
