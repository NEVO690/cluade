"""Characters: data helpers, abilities and the procedural runner model.

Characters are defined in ``data/characters.json``.  Each one has colours,
a hair style, an accessory and an ability.  The runner is drawn with simple
shapes (capsule limbs) and animated procedurally; real sprite frames can be
supplied per character (see assets.py / README) and will be used instead.
"""
import math

import pygame

from .utils import shade

ABILITY_TYPES = ("none", "coin_bonus", "jump_bonus", "powerup_duration", "score_bonus",
                 "magnet_start", "shield_start", "xp_bonus")


def build_look(gamedata, character_id, outfit_id=None):
    """Merge a character's colours with an outfit's colour overrides."""
    ch = gamedata.character(character_id)
    look = dict(ch["colors"])
    if outfit_id:
        outfit = gamedata.item(outfit_id)
        if outfit and outfit.get("category") == "outfits":
            look.update(outfit.get("colors", {}))
    look["hair_style"] = ch.get("hair_style", "short")
    look["accessory"] = ch.get("accessory", "none")
    look["build"] = ch.get("build", 1.0)
    look["id"] = ch["id"]
    return look


def ability(gamedata, character_id, kind):
    ab = gamedata.character(character_id).get("ability", {})
    return ab.get("value", 0) if ab.get("type") == kind else 0


# ---------------------------------------------------------------------------
# Procedural runner
# ---------------------------------------------------------------------------
def _pose_joints(pose, phase, t):
    """Return joint positions in metres relative to the feet (x right, y up).

    Keys: hip, l_knee, l_foot, r_knee, r_foot, chest, neck, head,
          l_elbow, l_hand, r_elbow, r_hand, squash (vertical scale of body).
    """
    j = {}
    if pose == "run":
        bob = abs(math.sin(phase)) * 0.06
        hip_y = 0.86 + bob
        for side, sgn, off in (("l", -1, 0.0), ("r", 1, math.pi)):
            s = math.sin(phase + off)
            hx = 0.1 * sgn
            if s > 0:  # leg swinging back - lifted foot
                j[side + "_knee"] = (hx + 0.02 * sgn, 0.48 + 0.12 * s + bob)
                j[side + "_foot"] = (hx + 0.03 * sgn, 0.12 + 0.42 * s + bob)
            else:
                j[side + "_knee"] = (hx, 0.46 + bob * 0.5 - 0.05 * s)
                j[side + "_foot"] = (hx, 0.02 - 0.02 * s)
            a = math.sin(phase + off + math.pi)
            j[side + "_elbow"] = (0.31 * sgn, 1.12 + 0.08 * a + bob)
            j[side + "_hand"] = (0.29 * sgn, 0.92 + 0.22 * a + bob)
        j["hip"] = (0.0, hip_y)
        j["chest"] = (0.0, 1.36 + bob)
        j["head"] = (0.0, 1.57 + bob)
    elif pose == "jump":
        j["hip"] = (0.0, 0.92)
        j["l_knee"] = (-0.2, 0.62)
        j["l_foot"] = (-0.14, 0.32)
        j["r_knee"] = (0.2, 0.66)
        j["r_foot"] = (0.16, 0.38)
        j["chest"] = (0.0, 1.38)
        j["head"] = (0.0, 1.6)
        j["l_elbow"] = (-0.42, 1.48)
        j["l_hand"] = (-0.5, 1.72)
        j["r_elbow"] = (0.42, 1.48)
        j["r_hand"] = (0.5, 1.72)
    elif pose == "slide":
        wob = math.sin(t * 30) * 0.02
        j["hip"] = (0.0, 0.42)
        j["l_knee"] = (-0.3, 0.3)
        j["l_foot"] = (-0.38, 0.05)
        j["r_knee"] = (0.3, 0.3)
        j["r_foot"] = (0.38, 0.05)
        j["chest"] = (0.0, 0.66 + wob)
        j["head"] = (0.0, 0.8 + wob)
        j["l_elbow"] = (-0.36, 0.5)
        j["l_hand"] = (-0.46, 0.2)
        j["r_elbow"] = (0.36, 0.5)
        j["r_hand"] = (0.46, 0.2)
    elif pose == "fall":
        j["hip"] = (0.0, 0.5)
        j["l_knee"] = (-0.32, 0.6)
        j["l_foot"] = (-0.5, 0.75)
        j["r_knee"] = (0.32, 0.55)
        j["r_foot"] = (0.52, 0.7)
        j["chest"] = (0.05, 0.95)
        j["head"] = (0.1, 1.15)
        j["l_elbow"] = (-0.45, 1.1)
        j["l_hand"] = (-0.6, 1.3)
        j["r_elbow"] = (0.45, 1.15)
        j["r_hand"] = (0.62, 1.35)
    else:  # idle / wave / cheer
        breath = math.sin(t * 2.2) * 0.012
        j["hip"] = (0.0, 0.86)
        j["l_knee"] = (-0.11, 0.45)
        j["l_foot"] = (-0.12, 0.0)
        j["r_knee"] = (0.11, 0.45)
        j["r_foot"] = (0.12, 0.0)
        j["chest"] = (0.0, 1.36 + breath)
        j["head"] = (0.0, 1.57 + breath)
        j["l_elbow"] = (-0.3, 1.12)
        j["l_hand"] = (-0.31, 0.88)
        if pose == "wave":
            w = math.sin(t * 9) * 0.12
            j["r_elbow"] = (0.42, 1.4)
            j["r_hand"] = (0.5 + w, 1.72)
        elif pose == "cheer":
            jump = abs(math.sin(t * 6)) * 0.12
            for k in list(j):
                j[k] = (j[k][0], j[k][1] + jump)
            j["l_elbow"] = (-0.4, 1.5 + jump)
            j["l_hand"] = (-0.46, 1.8 + jump)
            j["r_elbow"] = (0.4, 1.5 + jump)
            j["r_hand"] = (0.46, 1.8 + jump)
        else:
            j["r_elbow"] = (0.3, 1.12)
            j["r_hand"] = (0.31, 0.88)
    return j


def draw_runner(surf, x, y, scale, look, pose="run", phase=0.0, t=0.0, facing="back", lean=0.0, outline=False):
    """Draw a runner whose feet are at screen (x, y); ``scale`` = pixels per metre."""
    if scale < 2:
        return
    j = _pose_joints(pose, phase, t)
    build = look.get("build", 1.0)
    sk = look["skin"]
    hair = look["hair"]
    shirt = look["shirt"]
    pants = look["pants"]
    shoes = look["shoes"]
    accent = look["accent"]
    front = facing == "front"
    mirror = -1 if front else 1

    def P(pt, upper=False):
        px, py = pt
        if upper:
            px += lean * 0.18 * (py / 1.6)
        return (x + px * scale * build * mirror, y - py * scale)

    def limb(a, b, width_m, color):
        w = max(2, int(width_m * scale * build))
        pygame.draw.line(surf, color, a, b, w)
        r = w // 2
        if r >= 2:
            pygame.draw.circle(surf, color, (int(b[0]), int(b[1])), r)
            pygame.draw.circle(surf, color, (int(a[0]), int(a[1])), r)

    hip = P(j["hip"])
    chest = P(j["chest"], True)
    head = P(j["head"], True)
    detail = scale > 18

    # outline pass (menus): a slightly larger dark silhouette of the limbs
    if outline and scale > 40:
        ol = (16, 16, 26)
        for side in ("l", "r"):
            limb(hip, P(j[side + "_knee"]), 0.2, ol)
            limb(P(j[side + "_knee"]), P(j[side + "_foot"]), 0.18, ol)
            limb(P(j[side + "_elbow"], True), P(j[side + "_hand"], True), 0.14, ol)
        pygame.draw.circle(surf, ol, (int(head[0]), int(head[1])), int(0.15 * scale * build) + 3)

    # legs
    for side in ("l", "r"):
        knee = P(j[side + "_knee"])
        foot = P(j[side + "_foot"])
        limb(hip, knee, 0.15, pants)
        limb(knee, foot, 0.13, shade(pants, 0.85))
        sw = 0.16 * scale * build
        pygame.draw.ellipse(surf, shoes, (foot[0] - sw * 0.6, foot[1] - sw * 0.45, sw * 1.2, sw * 0.8))
        if detail:
            pygame.draw.ellipse(surf, accent, (foot[0] - sw * 0.6, foot[1] - sw * 0.05, sw * 1.2, sw * 0.3))

    # torso (trapezoid)
    hw_top = 0.25 * scale * build
    hw_bot = 0.19 * scale * build
    torso = [(chest[0] - hw_top, chest[1] - 0.02 * scale), (chest[0] + hw_top, chest[1] - 0.02 * scale),
             (hip[0] + hw_bot, hip[1] + 0.04 * scale), (hip[0] - hw_bot, hip[1] + 0.04 * scale)]
    pygame.draw.polygon(surf, shirt, torso)
    if detail:
        # belt + shirt accent stripe
        pygame.draw.line(surf, shade(pants, 0.7), (hip[0] - hw_bot, hip[1]), (hip[0] + hw_bot, hip[1]),
                         max(1, int(0.04 * scale)))
        mid_y = (chest[1] + hip[1]) / 2
        pygame.draw.line(surf, accent, (chest[0] - hw_top * 0.92, mid_y - 0.05 * scale),
                         (chest[0] + hw_top * 0.92, mid_y - 0.05 * scale), max(1, int(0.035 * scale)))
        if not front:  # backpack strap hint
            pygame.draw.rect(surf, shade(shirt, 0.75), (chest[0] - hw_top * 0.5, chest[1] + 0.04 * scale,
                                                         hw_top, (hip[1] - chest[1]) * 0.55), border_radius=3)

    # arms
    for side, sx in (("l", -1), ("r", 1)):
        sh = P((j["chest"][0] + 0.23 * sx, j["chest"][1] - 0.03), True)
        el = P(j[side + "_elbow"], True)
        hd = P(j[side + "_hand"], True)
        limb(sh, el, 0.11, shirt)
        limb(el, hd, 0.09, sk)

    # neck + head
    hr = 0.15 * scale * build
    pygame.draw.circle(surf, sk, (int(head[0]), int(head[1])), max(2, int(hr)))
    if detail:
        _draw_hair(surf, head, hr, look["hair_style"], hair, front)
        if front:
            ey = head[1] - hr * 0.05
            for ex in (-0.38, 0.38):
                pygame.draw.circle(surf, (255, 255, 255), (int(head[0] + ex * hr), int(ey)), max(1, int(hr * 0.22)))
                pygame.draw.circle(surf, (30, 30, 40), (int(head[0] + ex * hr + 1), int(ey)), max(1, int(hr * 0.12)))
            pygame.draw.arc(surf, (120, 50, 50), (head[0] - hr * 0.35, head[1] + hr * 0.15, hr * 0.7, hr * 0.45),
                            math.pi * 1.1, math.pi * 1.9, max(1, int(hr * 0.1)))
        _draw_accessory(surf, head, hr, look["accessory"], accent, front)


def _draw_hair(surf, head, r, style, color, front):
    hx, hy = head
    if style == "bald":
        return
    if style == "spiky":
        pts = [(hx - r, hy - r * 0.1)]
        for i in range(6):
            a = math.pi + i * math.pi / 5
            rr = r * (1.45 if i % 2 else 1.05)
            pts.append((hx + math.cos(a) * rr, hy + math.sin(a) * rr))
        pts.append((hx + r, hy - r * 0.1))
        pygame.draw.polygon(surf, color, pts)
    elif style == "mohawk":
        pygame.draw.ellipse(surf, color, (hx - r * 0.3, hy - r * 1.6, r * 0.6, r * 1.8))
    elif style == "bun":
        pygame.draw.circle(surf, color, (int(hx), int(hy - r * 0.95)), max(1, int(r * 0.45)))
        pygame.draw.ellipse(surf, color, (hx - r, hy - r * 1.02, r * 2, r * 1.2))
    elif style == "long":
        pygame.draw.ellipse(surf, color, (hx - r * 1.02, hy - r * 1.05, r * 2.04, r * 1.3))
        if not front:
            pygame.draw.rect(surf, color, (hx - r * 0.95, hy - r * 0.2, r * 1.9, r * 1.6), border_radius=int(r * 0.5))
        else:
            pygame.draw.rect(surf, color, (hx - r * 1.05, hy - r * 0.3, r * 0.4, r * 1.5), border_radius=int(r * 0.3))
            pygame.draw.rect(surf, color, (hx + r * 0.65, hy - r * 0.3, r * 0.4, r * 1.5), border_radius=int(r * 0.3))
    else:  # short
        pygame.draw.ellipse(surf, color, (hx - r * 1.02, hy - r * 1.05, r * 2.04, r * 1.2))
    if not front and style != "mohawk":
        # back of the head is mostly hair
        pygame.draw.ellipse(surf, color, (hx - r * 0.98, hy - r * 0.9, r * 1.96, r * 1.55))


def _draw_accessory(surf, head, r, kind, color, front):
    hx, hy = head
    w = max(1, int(r * 0.22))
    if kind == "cap":
        pygame.draw.ellipse(surf, color, (hx - r * 1.05, hy - r * 1.15, r * 2.1, r * 1.1))
        if front:
            pygame.draw.ellipse(surf, shade(color, 0.8), (hx - r * 0.9, hy - r * 0.45, r * 1.8, r * 0.4))
        else:
            pygame.draw.rect(surf, shade(color, 0.7), (hx - r * 0.35, hy - r * 0.35, r * 0.7, r * 0.18))
    elif kind == "headphones":
        pygame.draw.arc(surf, (40, 40, 50), (hx - r * 1.1, hy - r * 1.25, r * 2.2, r * 2.0), 0, math.pi, w)
        for sx in (-1, 1):
            pygame.draw.ellipse(surf, color, (hx + sx * r * 0.95 - r * 0.3, hy - r * 0.35, r * 0.6, r * 0.75))
    elif kind == "goggles":
        pygame.draw.line(surf, (40, 40, 50), (hx - r, hy - r * 0.35), (hx + r, hy - r * 0.35), w)
        if front:
            for sx in (-1, 1):
                pygame.draw.circle(surf, color, (int(hx + sx * r * 0.42), int(hy - r * 0.35)), max(1, int(r * 0.32)))
    elif kind == "bandana":
        pygame.draw.line(surf, color, (hx - r, hy - r * 0.45), (hx + r, hy - r * 0.45), max(2, int(r * 0.32)))
        if not front:
            pygame.draw.polygon(surf, color, [(hx, hy - r * 0.45), (hx - r * 0.2, hy + r * 0.3), (hx + r * 0.25, hy + r * 0.2)])
    elif kind == "visor":
        pygame.draw.line(surf, color, (hx - r * 1.05, hy - r * 0.2), (hx + r * 1.05, hy - r * 0.2), max(2, int(r * 0.4)))


def draw_board(surf, x, y, scale, board, t=0.0, angle_ratio=0.35):
    """Draw a board seen from behind/above at screen position (x, y) (board centre)."""
    deck = board["colors"]["deck"]
    stripe = board["colors"]["stripe"]
    w = 0.42 * scale
    h = max(2, 0.9 * scale * angle_ratio)
    style = board.get("style", "street")
    if style == "hover":
        glow = board["colors"]["glow"]
        pygame.draw.ellipse(surf, shade(glow, 0.6), (x - w * 1.1, y - h * 0.2 + 0.18 * scale, w * 2.2, h * 0.7))
    pygame.draw.ellipse(surf, shade(deck, 0.6), (x - w, y - h / 2 + 2, w * 2, h))
    pygame.draw.ellipse(surf, deck, (x - w, y - h / 2, w * 2, h))
    pygame.draw.line(surf, stripe, (x - w * 0.7, y), (x + w * 0.7, y), max(1, int(0.06 * scale)))
    if style in ("street", "cyber"):
        for sx in (-0.6, 0.6):
            pygame.draw.circle(surf, (30, 30, 30), (int(x + sx * w), int(y + h * 0.45)), max(1, int(0.07 * scale)))
