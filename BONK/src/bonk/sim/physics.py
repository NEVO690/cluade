"""Kinematic character controller: input -> velocity -> collision-resolved movement.

The same code runs on the client (single player), the bots and the
multiplayer server, so all three obey exactly the same rules.
"""

import math

from . import constants as C
from .character import MoveState
from .geometry import circle_overlaps_rect, circle_rect_push, wrap_angle

SUPPORT_RADIUS = C.CHAR_RADIUS * 0.6  # how far over an edge you can stand before slipping off


def step_character(ch, cmd, world, t, dt):
    """Advance one character by one fixed tick.  `world.update(t)` must run first."""
    was_grounded = ch.grounded

    # ---- timers -----------------------------------------------------------
    ch.stun = max(0.0, ch.stun - dt)
    ch.grace = max(0.0, ch.grace - dt)
    ch.land_timer = max(0.0, ch.land_timer - dt)
    ch.coyote = max(0.0, ch.coyote - dt)
    ch.jump_buffer = max(0.0, ch.jump_buffer - dt)

    # ---- input -------------------------------------------------------------
    mx, my = cmd.move_x, cmd.move_y
    m = math.hypot(mx, my)
    if m > 1.0:
        mx, my, m = mx / m, my / m, 1.0
    if cmd.jump and not ch.jump_held:
        ch.jump_buffer = C.JUMP_BUFFER  # press edge only: holding jump never repeats
    ch.jump_held = cmd.jump

    top_speed = C.WALK_SPEED if cmd.walk else C.RUN_SPEED
    tvx, tvy = mx * top_speed, my * top_speed
    ch.wish_speed = top_speed * m

    if ch.grounded:
        accel = C.GROUND_ACCEL if m > 0.05 else C.GROUND_DECEL
    else:
        accel = C.AIR_ACCEL
    if ch.stun > 0.0:
        accel *= C.STUN_CONTROL
    dvx, dvy = tvx - ch.vx, tvy - ch.vy
    dl = math.hypot(dvx, dvy)
    max_dv = accel * dt
    if dl > max_dv:
        dvx, dvy = dvx / dl * max_dv, dvy / dl * max_dv
    ch.vx += dvx
    ch.vy += dvy

    # Body faces where it is going (or where the input points, for snappy turning).
    if ch.stun <= 0.0 and m > 0.1:
        target = math.atan2(-mx, my)
        ch.yaw += wrap_angle(target - ch.yaw) * min(1.0, C.TURN_RATE * dt)
        ch.yaw = wrap_angle(ch.yaw)

    # ---- jump --------------------------------------------------------------
    if ch.jump_buffer > 0.0 and (ch.grounded or ch.coyote > 0.0) and ch.stun <= 0.0:
        ch.vz = C.JUMP_SPEED
        ch.grounded = False
        ch.ground = None
        ch.coyote = 0.0
        ch.jump_buffer = 0.0
        ch.jumped = True
        ch.land_timer = 0.0
        ch.stat_jumps += 1
        ch.events.append(("jump", None))

    # ---- moving-platform carry ---------------------------------------------
    if ch.grounded and ch.ground is not None and ch.ground.moving:
        g = ch.ground
        ch.x += g.dx
        ch.y += g.dy
        ch.z += g.dz

    # ---- gravity -----------------------------------------------------------
    if not ch.grounded:
        ch.vz = max(ch.vz - C.GRAVITY * dt, -C.MAX_FALL_SPEED)

    # ---- horizontal movement ---------------------------------------------------
    ch.x += ch.vx * dt
    ch.y += ch.vy * dt
    solids = world.solids_near(ch.y, 2.0)
    _resolve_walls(ch, solids, t)

    # ---- vertical movement -------------------------------------------------
    prev_z = ch.z
    ch.z += ch.vz * dt
    _resolve_vertical(ch, solids, prev_z, was_grounded, t)

    if was_grounded and not ch.grounded and ch.vz <= 0.0:
        ch.coyote = C.COYOTE_TIME
    ch.air_time = 0.0 if ch.grounded else ch.air_time + dt

    # ---- hazards -----------------------------------------------------------
    for h in world.hazards_near(ch.y, 4.0):
        h.collide(ch, t)

    ch.state = classify_state(ch)


def _resolve_walls(ch, solids, t):
    r = C.CHAR_RADIUS
    feet, head = ch.z, ch.z + C.CHAR_HEIGHT
    for _ in range(2):
        moved = False
        for s in solids:
            if not s.is_solid() or head <= s.minz + 1e-3 or feet >= s.maxz - 1e-3:
                continue
            if s.maxx < ch.x - r or s.minx > ch.x + r or s.maxy < ch.y - r or s.miny > ch.y + r:
                continue
            top = s.top_at(min(max(ch.x, s.minx), s.maxx), min(max(ch.y, s.miny), s.maxy))
            if feet + C.STEP_HEIGHT >= top:
                continue  # low enough to step onto; vertical pass handles it
            push = circle_rect_push(ch.x, ch.y, r, s.minx, s.miny, s.maxx, s.maxy)
            if push is None:
                continue
            px, py = push
            ch.x += px
            ch.y += py
            pl = math.hypot(px, py)
            if pl > 1e-9:
                nx, ny = px / pl, py / pl
                vn = ch.vx * nx + ch.vy * ny
                if vn < 0.0:
                    ch.vx -= vn * nx
                    ch.vy -= vn * ny
                if s.knock > 0.0 and (s.vx * nx + s.vy * ny) > 1.0:
                    ch.hit_by(s.id, t, nx, ny, s.vx, s.vy, s.knock, 4.5)
            moved = True
        if not moved:
            break


def _resolve_vertical(ch, solids, prev_z, was_grounded, t):
    best_top, best = None, None
    if ch.vz <= 0.0:
        upper = prev_z + (C.STEP_HEIGHT if was_grounded else 0.05)
        lower = ch.z - (C.GROUND_SNAP if was_grounded else 0.0)
        for s in solids:
            if not s.is_solid():
                continue
            if not circle_overlaps_rect(ch.x, ch.y, SUPPORT_RADIUS, s.minx, s.miny, s.maxx, s.maxy):
                continue
            top = s.top_at(min(max(ch.x, s.minx), s.maxx), min(max(ch.y, s.miny), s.maxy))
            if lower - 1e-4 <= top <= upper and (best_top is None or top > best_top):
                best_top, best = top, s
    if best is not None:
        impact = -ch.vz
        ch.z = best_top
        ch.vz = 0.0
        if not was_grounded:
            ch.events.append(("land", impact))
            if impact >= C.HARD_LANDING_SPEED:
                ch.land_timer = C.LAND_TIME
        ch.grounded = True
        ch.ground = best
        ch.jumped = False
        best.on_stand(ch, t)
        if best.bounce > 0.0:
            ch.vz = best.bounce
            ch.grounded = False
            ch.ground = None
            ch.jumped = True
            ch.land_timer = 0.0
            ch.events.append(("bounce", best.id))
        return
    ch.grounded = False
    ch.ground = None
    if ch.vz > 0.0:
        head_prev = prev_z + C.CHAR_HEIGHT
        head = ch.z + C.CHAR_HEIGHT
        for s in solids:
            if not s.is_solid():
                continue
            if s.minz >= head_prev - 0.05 and head > s.minz and circle_overlaps_rect(
                    ch.x, ch.y, SUPPORT_RADIUS, s.minx, s.miny, s.maxx, s.maxy):
                ch.z = s.minz - C.CHAR_HEIGHT
                ch.vz = 0.0
                ch.events.append(("ceiling", s.id))
                break


def classify_state(ch):
    if ch.eliminated:
        return MoveState.ELIMINATED
    if ch.respawn_timer > 0.0:
        return MoveState.RESPAWNING
    if ch.finished or ch.celebrate:
        return MoveState.VICTORY
    if ch.stun > 0.0:
        return MoveState.TUMBLE
    if not ch.grounded:
        if ch.jumped and ch.vz > 0.0:
            return MoveState.JUMP
        # Short drops (stepping off a curb) keep the ground state to avoid flicker.
        if ch.air_time < 0.12 and not ch.jumped and ch.state in (MoveState.WALK, MoveState.RUN, MoveState.IDLE):
            return ch.state
        return MoveState.FALL
    if ch.land_timer > 0.0:
        return MoveState.LAND
    sp = ch.speed
    if sp < 0.4:
        return MoveState.IDLE
    if sp < (C.WALK_SPEED + C.RUN_SPEED) * 0.5:
        return MoveState.WALK
    return MoveState.RUN


def resolve_character_pairs(chars):
    """Characters push each other apart; landing on someone's head is a BONK."""
    bodies = [c for c in chars if c.active and not c.eliminated and c.respawn_timer <= 0.0]
    bodies.sort(key=lambda c: c.y)
    two_r = 2.0 * C.CHAR_RADIUS
    n = len(bodies)
    for i in range(n):
        a = bodies[i]
        for j in range(i + 1, n):
            b = bodies[j]
            if b.y - a.y >= two_r:
                break
            dz = a.z - b.z
            if abs(dz) >= C.CHAR_HEIGHT:
                continue
            dx, dy = b.x - a.x, b.y - a.y
            d2 = dx * dx + dy * dy
            if d2 >= two_r * two_r:
                continue
            top, bottom = (a, b) if dz > 0 else (b, a)
            if abs(dz) > C.CHAR_HEIGHT * 0.6 and top.vz <= 0.5:
                _head_bonk(top, bottom)
                continue
            d = math.sqrt(d2)
            if d < 1e-6:
                dx, dy, d = 1.0, 0.0, 1.0
            nx, ny = dx / d, dy / d
            overlap = (two_r - d) * C.PUSH_STRENGTH
            a.x -= nx * overlap
            a.y -= ny * overlap
            b.x += nx * overlap
            b.y += ny * overlap
            # Exchange part of the approaching velocity (soft bump).
            rel = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny
            if rel > 0.0:
                imp = rel * 0.5
                a.vx -= nx * imp
                a.vy -= ny * imp
                b.vx += nx * imp
                b.vy += ny * imp


def _head_bonk(top, bottom):
    top.z = bottom.z + C.CHAR_HEIGHT
    top.vz = C.HEAD_BONK_SPEED
    top.grounded = False
    top.ground = None
    top.jumped = True
    top.stat_bonks += 1
    top.events.append(("bonk", bottom.id))
    if bottom.grace <= 0.0 and not bottom.finished:
        bottom.stun = max(bottom.stun, C.HEAD_BONK_STUN)
        bottom.events.append(("bonked", top.id))
