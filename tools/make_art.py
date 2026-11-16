"""Generates the TAF placeholder character art (layered parts) + rig.json.

Every part is its own PNG so the mod can animate them independently
(breathing, blinking, mouth flaps, arm swings...). To replace the art later,
draw new PNGs with the same file names (UHD scale: 4 px per GD point) and,
if the proportions change, update rig.json.
"""
import json, math, os, sys
from PIL import Image, ImageDraw, ImageFilter

S = 4  # pixels per point (UHD)
OUT = sys.argv[1] if len(sys.argv) > 1 else "resources/sprites"
os.makedirs(OUT, exist_ok=True)
OUTLINE = (20, 16, 28, 255)
LW = 3 * S  # outline width


def canvas(w, h):
    return Image.new("RGBA", (int(w * S), int(h * S)), (0, 0, 0, 0))


def P(*pts):
    return [(x * S, y * S) for x, y in pts]


def box(x0, y0, x1, y1):
    return [x0 * S, y0 * S, x1 * S, y1 * S]


def save(img, name):
    img.save(os.path.join(OUT, name))


def soft_shadow_shine(img):
    return img


# ---------------------------------------------------------------- Aura Farmer
# Image coordinates: y grows downward inside each canvas.
def af_legs():
    im = canvas(40, 50); d = ImageDraw.Draw(im)
    for x in (6, 22):
        d.rounded_rectangle(box(x, 2, x + 12, 44), 3 * S, fill=(38, 44, 70), outline=OUTLINE, width=LW)
        d.rounded_rectangle(box(x - 3, 40, x + 15, 49), 3 * S, fill=(235, 235, 245), outline=OUTLINE, width=LW)
    save(im, "af_legs.png")


def af_torso():
    im = canvas(56, 60); d = ImageDraw.Draw(im)
    d.rounded_rectangle(box(3, 3, 53, 58), 12 * S, fill=(30, 30, 48), outline=OUTLINE, width=LW)
    d.rectangle(box(26, 8, 30, 56), fill=(70, 230, 255))  # glowing zipper stripe
    d.line(P((12, 14), (22, 30)), fill=(70, 230, 255), width=2 * S)
    d.line(P((44, 14), (34, 30)), fill=(70, 230, 255), width=2 * S)
    save(im, "af_torso.png")


def af_arm(name):
    im = canvas(18, 52); d = ImageDraw.Draw(im)
    d.rounded_rectangle(box(3, 2, 15, 42), 6 * S, fill=(30, 30, 48), outline=OUTLINE, width=LW)
    d.ellipse(box(2, 38, 16, 51), fill=(240, 196, 160), outline=OUTLINE, width=LW)
    save(im, name)


def af_head():
    im = canvas(60, 64); d = ImageDraw.Draw(im)
    d.ellipse(box(7, 14, 53, 60), fill=(240, 196, 160), outline=OUTLINE, width=LW)
    # spiky hair
    spikes = [(5, 30), (8, 12), (16, 18), (20, 2), (30, 13), (38, 1), (42, 14), (54, 6), (52, 22), (57, 30),
              (50, 24), (40, 20), (28, 22), (16, 24)]
    d.polygon(P(*spikes), fill=(25, 22, 35), outline=OUTLINE, width=LW)
    d.line(P((22, 6), (26, 16)), fill=(80, 220, 255), width=2 * S)  # aura streak
    save(im, "af_head.png")


def eyes(prefix, w, h, iris, angry_col):
    # open
    im = canvas(w, h); d = ImageDraw.Draw(im)
    for cx in (w * 0.27, w * 0.73):
        d.ellipse(box(cx - 5, 1, cx + 5, h - 1), fill=(255, 255, 255), outline=OUTLINE, width=2 * S)
        d.ellipse(box(cx - 1, h * 0.3, cx + 4, h * 0.8), fill=iris)
    save(im, f"{prefix}_eyes_open.png")
    # closed (blink)
    im = canvas(w, h); d = ImageDraw.Draw(im)
    for cx in (w * 0.27, w * 0.73):
        d.arc(box(cx - 5, h * 0.1, cx + 5, h * 0.8), 20, 160, fill=OUTLINE, width=2 * S)
    save(im, f"{prefix}_eyes_closed.png")
    # angry
    im = canvas(w, h); d = ImageDraw.Draw(im)
    for i, cx in enumerate((w * 0.27, w * 0.73)):
        d.pieslice(box(cx - 5, 1, cx + 5, h - 1), 0, 180, fill=(255, 255, 255), outline=OUTLINE, width=2 * S)
        d.ellipse(box(cx - 1, h * 0.5, cx + 3, h * 0.85), fill=angry_col)
        if i == 0:
            d.line(P((cx - 6, 1), (cx + 6, h * 0.5)), fill=OUTLINE, width=2 * S)
        else:
            d.line(P((cx - 6, h * 0.5), (cx + 6, 1)), fill=OUTLINE, width=2 * S)
    save(im, f"{prefix}_eyes_angry.png")


def af_mouths():
    for name, open_h in (("closed", 0), ("mid", 4), ("open", 8)):
        im = canvas(20, 12); d = ImageDraw.Draw(im)
        if open_h == 0:
            d.arc(box(3, -4, 17, 7), 30, 150, fill=OUTLINE, width=2 * S)
        else:
            d.ellipse(box(10 - 4 - open_h * 0.3, 6 - open_h / 2, 10 + 4 + open_h * 0.3, 6 + open_h / 2 + 0.5),
                      fill=(120, 30, 40), outline=OUTLINE, width=2 * S)
        save(im, f"af_mouth_{name}.png")


def aura():
    W, H = 170, 200
    im = canvas(W, H)
    px = im.load()
    cx, cy = W * S / 2, H * S / 2
    for y in range(im.height):
        for x in range(im.width):
            dx = (x - cx) / (W * S / 2); dy = (y - cy) / (H * S / 2)
            r = math.sqrt(dx * dx + dy * dy)
            if r < 1:
                a = (1 - r) ** 1.6
                px[x, y] = (int(60 + 120 * (1 - r)), int(200 + 40 * (1 - r)), 255, int(210 * a))
    save(im, "af_aura.png")


# ---------------------------------------------------------------- Chicken
def ck_legs():
    im = canvas(34, 24); d = ImageDraw.Draw(im)
    for x in (10, 22):
        d.line(P((x, 0), (x, 20)), fill=(240, 150, 30), width=3 * S)
        d.line(P((x - 5, 22), (x + 6, 22)), fill=(240, 150, 30), width=3 * S)
    save(im, "ck_legs.png")


def ck_body():
    im = canvas(90, 70); d = ImageDraw.Draw(im)
    # tail feathers (left = back, chicken faces right)
    d.polygon(P((14, 30), (0, 6), (10, 12), (8, 0), (20, 14), (24, 8), (26, 26)), fill=(250, 250, 250), outline=OUTLINE, width=LW)
    d.ellipse(box(8, 10, 86, 68), fill=(250, 250, 250), outline=OUTLINE, width=LW)
    d.chord(box(14, 40, 80, 66), 10, 170, fill=(230, 230, 236))
    save(im, "ck_body.png")


def ck_wing():
    im = canvas(38, 30); d = ImageDraw.Draw(im)
    d.polygon(P((3, 4), (34, 8), (30, 18), (24, 26), (14, 27), (5, 20)), fill=(238, 238, 244), outline=OUTLINE, width=LW)
    d.line(P((12, 12), (28, 14)), fill=(190, 190, 200), width=2 * S)
    d.line(P((12, 19), (24, 20)), fill=(190, 190, 200), width=2 * S)
    save(im, "ck_wing.png")


def ck_head():
    im = canvas(50, 58); d = ImageDraw.Draw(im)
    d.ellipse(box(5, 12, 47, 54), fill=(250, 250, 250), outline=OUTLINE, width=LW)
    d.polygon(P((12, 20), (13, 5), (20, 12), (25, 1), (30, 12), (37, 5), (39, 20), (26, 16)), fill=(230, 40, 50), outline=OUTLINE, width=2 * S)
    d.ellipse(box(36, 40, 44, 52), fill=(230, 40, 50), outline=OUTLINE, width=2 * S)  # wattle
    save(im, "ck_head.png")


def ck_beaks():
    for name, gap in (("closed", 0), ("mid", 3), ("open", 6)):
        im = canvas(26, 24); d = ImageDraw.Draw(im)
        top = 12 - gap / 2
        d.polygon(P((2, top - 8), (24, top), (2, top)), fill=(255, 190, 40), outline=OUTLINE, width=S + S // 2)
        d.polygon(P((2, 12 + gap / 2), (18, 12 + gap / 2), (2, 12 + gap / 2 + 6)), fill=(240, 150, 30), outline=OUTLINE, width=S + S // 2)
        if gap:
            d.rectangle(box(2.5, top + 0.5, 6, 12 + gap / 2 - 0.5), fill=(120, 30, 40))
        save(im, f"ck_mouth_{name}.png")


def menu_icon():
    im = canvas(40, 40); d = ImageDraw.Draw(im)
    d.ellipse(box(2, 2, 38, 38), fill=(70, 230, 255, 90))
    d.ellipse(box(8, 8, 32, 32), fill=(240, 196, 160), outline=OUTLINE, width=LW)
    d.polygon(P((7, 18), (10, 6), (16, 11), (20, 3), (25, 10), (32, 5), (33, 18), (20, 14)), fill=(25, 22, 35), outline=OUTLINE, width=2 * S)
    for cx in (15, 25):
        d.ellipse(box(cx - 3, 18, cx + 3, 25), fill=(255, 255, 255), outline=OUTLINE, width=S)
    save(im, "taf_icon.png")


af_legs(); af_torso(); af_arm("af_arm_back.png"); af_arm("af_arm_front.png"); af_head()
eyes("af", 30, 12, (30, 140, 200), (30, 140, 200)); af_mouths(); aura()
ck_legs(); ck_body(); ck_wing(); ck_head(); eyes("ck", 22, 10, (20, 16, 28), (20, 16, 28)); ck_beaks()
menu_icon()

# rig.json -- positions in GD points. Root = feet centre, y up. Characters face RIGHT;
# the mod mirrors the one standing on the right side.
rig = {
    "aura": {
        "parts": [
            {"id": "aura", "sprite": "af_aura.png", "pos": [0, 75], "anchor": [0.5, 0.5], "z": -10, "additive": True},
            {"id": "arm_back", "sprite": "af_arm_back.png", "pos": [-20, 96], "anchor": [0.5, 0.92], "z": -1, "color": [200, 200, 215]},
            {"id": "legs", "sprite": "af_legs.png", "pos": [0, 0], "anchor": [0.5, 0], "z": 0},
            {"id": "torso", "sprite": "af_torso.png", "pos": [0, 42], "anchor": [0.5, 0], "z": 1},
            {"id": "head", "sprite": "af_head.png", "pos": [0, 92], "anchor": [0.5, 0.1], "z": 2},
            {"id": "eyes", "sprite": "af_eyes_open.png", "parent": "head", "pos": [31, 29], "anchor": [0.5, 0.5], "z": 1},
            {"id": "mouth", "sprite": "af_mouth_closed.png", "parent": "head", "pos": [30, 14], "anchor": [0.5, 0.5], "z": 1},
            {"id": "arm_front", "sprite": "af_arm_front.png", "pos": [22, 96], "anchor": [0.5, 0.92], "z": 3}
        ],
        "eyes": {"open": "af_eyes_open.png", "closed": "af_eyes_closed.png", "angry": "af_eyes_angry.png"},
        "mouth": ["af_mouth_closed.png", "af_mouth_mid.png", "af_mouth_open.png"],
        "height": 150
    },
    "chicken": {
        "parts": [
            {"id": "legs", "sprite": "ck_legs.png", "pos": [0, 0], "anchor": [0.5, 0], "z": 0},
            {"id": "torso", "sprite": "ck_body.png", "pos": [-4, 18], "anchor": [0.5, 0], "z": 1},
            {"id": "head", "sprite": "ck_head.png", "pos": [24, 64], "anchor": [0.5, 0.15], "z": 2},
            {"id": "eyes", "sprite": "ck_eyes_open.png", "parent": "head", "pos": [32, 29], "anchor": [0.5, 0.5], "z": 1},
            {"id": "mouth", "sprite": "ck_mouth_closed.png", "parent": "head", "pos": [44, 23], "anchor": [0.1, 0.5], "z": 1},
            {"id": "arm_front", "sprite": "ck_wing.png", "pos": [-6, 50], "anchor": [0.15, 0.8], "z": 3}
        ],
        "eyes": {"open": "ck_eyes_open.png", "closed": "ck_eyes_closed.png", "angry": "ck_eyes_angry.png"},
        "mouth": ["ck_mouth_closed.png", "ck_mouth_mid.png", "ck_mouth_open.png"],
        "height": 120
    }
}
with open(os.path.join(os.path.dirname(OUT.rstrip("/")), "rig.json"), "w") as f:
    json.dump(rig, f, indent=2)
print("ok")
