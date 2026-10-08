"""Characters: data helpers, abilities and the 2D board icon.

Characters are defined in ``data/characters.json``.  Each one has colours,
a hair style, an accessory and an ability.  The 3D model built from those
settings lives in ``model3d.py``; real sprite frames can be supplied per
character (see assets.py / README) and will be used instead.
"""
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
