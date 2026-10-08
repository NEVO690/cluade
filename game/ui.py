"""UI toolkit: buttons, sliders, scrolling, toasts, panels and the in-run HUD."""
import pygame

from . import settings as S
from .utils import shade, clamp, fmt_int, lerp_color

_gradient_cache = {}


def gradient_rect(size, top, bottom, radius=0):
    key = (size, top, bottom, radius)
    surf = _gradient_cache.get(key)
    if surf is None:
        if len(_gradient_cache) > 300:
            _gradient_cache.clear()
        w, h = size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            c = lerp_color(top, bottom, y / max(1, h - 1))
            pygame.draw.line(surf, c, (0, y), (w, y))
        if radius:
            mask = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
            surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        _gradient_cache[key] = surf
    return surf


def panel(surf, rect, color=S.UI_PANEL, radius=18, border=None, shadow=True, alpha=None):
    rect = pygame.Rect(rect)
    if shadow:
        sh = pygame.Surface((rect.w + 8, rect.h + 8), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 90), (4, 6, rect.w, rect.h), border_radius=radius)
        surf.blit(sh, (rect.x - 4, rect.y - 2))
    if alpha is not None:
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (*color, alpha), (0, 0, rect.w, rect.h), border_radius=radius)
        surf.blit(layer, rect.topleft)
    else:
        surf.blit(gradient_rect(rect.size, shade(color, 1.18), shade(color, 0.9), radius), rect.topleft)
    if border:
        pygame.draw.rect(surf, border, rect, 3, border_radius=radius)


def progress_bar(surf, rect, frac, color=S.UI_ACCENT, bg=(20, 24, 44), radius=8):
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, bg, rect, border_radius=radius)
    frac = clamp(frac, 0, 1)
    if frac > 0:
        w = max(radius * 2, int(rect.w * frac))
        pygame.draw.rect(surf, color, (rect.x, rect.y, w, rect.h), border_radius=radius)
        pygame.draw.rect(surf, shade(color, 1.3), (rect.x + 4, rect.y + 3, w - 8, max(2, rect.h // 4)), border_radius=radius)


def blit_center(surf, img, center):
    surf.blit(img, (center[0] - img.get_width() // 2, center[1] - img.get_height() // 2))


def wrap_text(assets, text, size, width, bold=False):
    words = str(text).split()
    lines = []
    cur = ""
    font = assets.font(size, bold)
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(surf, assets, text, size, color, rect, bold=False, line_gap=2, max_lines=None):
    rect = pygame.Rect(rect)
    lines = wrap_text(assets, text, size, rect.w, bold)
    if max_lines:
        lines = lines[:max_lines]
    y = rect.y
    for ln in lines:
        img = assets.text(ln, size, color, bold)
        surf.blit(img, (rect.x, y))
        y += img.get_height() + line_gap
    return y


class Button:
    STYLES = {
        "primary": ((255, 196, 40), (40, 30, 10)),
        "secondary": ((70, 110, 230), (255, 255, 255)),
        "good": ((60, 200, 110), (255, 255, 255)),
        "danger": ((230, 70, 70), (255, 255, 255)),
        "dark": ((48, 58, 98), (255, 255, 255)),
        "ghost": ((36, 42, 74), (220, 225, 255)),
    }

    def __init__(self, rect, text="", on_click=None, style="primary", icon=None, size=30, enabled=True,
                 badge=None, sound="button", tooltip=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.on_click = on_click
        self.style = style
        self.icon = icon
        self.size = size
        self.enabled = enabled
        self.badge = badge
        self.sound = sound
        self.hover = False
        self.pressed = False
        self.anim = 0.0
        self.visible = True

    def handle(self, event, app=None):
        if not self.visible:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True  # consume
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            if was and self.rect.collidepoint(event.pos):
                if self.enabled:
                    if app is not None and self.sound:
                        app.audio.play(self.sound)
                    if self.on_click:
                        self.on_click()
                elif app is not None:
                    app.audio.play("error")
                return True
        return False

    def update(self, dt):
        target = 1.0 if self.hover and self.enabled else 0.0
        self.anim += (target - self.anim) * min(1.0, dt * 12)

    def draw(self, surf, assets):
        if not self.visible:
            return
        base, fg = self.STYLES.get(self.style, self.STYLES["primary"])
        if not self.enabled:
            base, fg = (70, 72, 90), (150, 150, 170)
        scale = 1.0 + 0.04 * self.anim - (0.05 if self.pressed else 0.0)
        r = self.rect.inflate(int(self.rect.w * (scale - 1)), int(self.rect.h * (scale - 1)))
        radius = min(22, r.h // 2)
        pygame.draw.rect(surf, shade(base, 0.55), r.move(0, 5), border_radius=radius)
        surf.blit(gradient_rect(r.size, shade(base, 1.2 + 0.1 * self.anim), shade(base, 0.92), radius), r.topleft)
        pygame.draw.rect(surf, shade(base, 1.4), r, 2, border_radius=radius)
        content = []
        if self.icon:
            content.append(assets.icon(self.icon, int(self.size * 1.25), fg if self.style != "primary" else (60, 40, 10)))
        if self.text:
            content.append(assets.text(self.text, self.size, fg))
        total_w = sum(c.get_width() for c in content) + (10 if len(content) > 1 else 0)
        x = r.centerx - total_w // 2
        for c in content:
            surf.blit(c, (x, r.centery - c.get_height() // 2))
            x += c.get_width() + 10
        if self.badge:
            b = assets.text(str(self.badge), 20, (255, 255, 255))
            br = pygame.Rect(0, 0, max(28, b.get_width() + 14), 28)
            br.center = (r.right - 6, r.top + 6)
            pygame.draw.rect(surf, S.UI_BAD, br, border_radius=14)
            blit_center(surf, b, br.center)


class Slider:
    def __init__(self, rect, value, on_change):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.on_change = on_change
        self.drag = False

    def handle(self, event, app=None):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.inflate(20, 30).collidepoint(event.pos):
            self.drag = True
            self._set(event.pos[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag:
                self.drag = False
                if app:
                    app.audio.play("button")
                return True
        if event.type == pygame.MOUSEMOTION and self.drag:
            self._set(event.pos[0])
            return True
        return False

    def _set(self, x):
        self.value = clamp((x - self.rect.x) / self.rect.w, 0, 1)
        self.on_change(self.value)

    def update(self, dt):
        pass

    def draw(self, surf, assets):
        progress_bar(surf, self.rect, self.value, S.UI_ACCENT_2, radius=self.rect.h // 2)
        kx = self.rect.x + self.rect.w * self.value
        pygame.draw.circle(surf, (255, 255, 255), (int(kx), self.rect.centery), self.rect.h)
        pygame.draw.circle(surf, S.UI_ACCENT_2, (int(kx), self.rect.centery), self.rect.h - 4)


class Scroller:
    """Vertical scrolling for a list area (mouse wheel + drag/touch)."""

    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.offset = 0.0
        self.content_h = 0
        self._drag_y = None
        self._drag_start = 0.0
        self.dragged = False
        self.vel = 0.0

    @property
    def max_offset(self):
        return max(0, self.content_h - self.rect.h)

    def handle(self, event):
        if event.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.offset = clamp(self.offset - event.y * 60, 0, self.max_offset)
                return True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._drag_y = event.pos[1]
            self._drag_start = self.offset
            self.dragged = False
        elif event.type == pygame.MOUSEMOTION and self._drag_y is not None:
            dy = event.pos[1] - self._drag_y
            if abs(dy) > 8:
                self.dragged = True
            if self.dragged:
                self.offset = clamp(self._drag_start - dy, 0, self.max_offset)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.dragged
            self._drag_y = None
            self.dragged = False
            return was
        return False

    def draw_bar(self, surf):
        if self.max_offset <= 0:
            return
        h = max(40, self.rect.h * self.rect.h / self.content_h)
        y = self.rect.y + (self.rect.h - h) * (self.offset / self.max_offset)
        pygame.draw.rect(surf, (110, 118, 160), (self.rect.right - 6, y, 5, h), border_radius=3)


class Toasts:
    def __init__(self, assets):
        self.assets = assets
        self.items = []

    def push(self, text, icon="star", color=S.UI_ACCENT, duration=2.8):
        if any(t[0] == text for t in self.items):
            return
        self.items.append([text, icon, color, duration, duration])
        if len(self.items) > 4:
            self.items.pop(0)

    def update(self, dt):
        for t in self.items:
            t[3] -= dt
        self.items = [t for t in self.items if t[3] > 0]

    def draw(self, surf, y=90):
        for i, (text, icon, color, life, dur) in enumerate(self.items):
            k = min(1.0, (dur - life) * 5, life * 4)
            img = self.assets.text(text, 24, (255, 255, 255))
            w = img.get_width() + 76
            rect = pygame.Rect(0, 0, w, 52)
            rect.centerx = S.SCREEN_W // 2
            rect.y = int(y + i * 60 - (1 - k) * 40)
            layer = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(layer, (20, 24, 46, int(230 * k)), (0, 0, rect.w, rect.h), border_radius=26)
            pygame.draw.rect(layer, (*color, int(255 * k)), (0, 0, rect.w, rect.h), 3, border_radius=26)
            ic = self.assets.icon(icon, 34, color)
            layer.blit(ic, (14, 9))
            img2 = img.copy()
            img2.set_alpha(int(255 * k))
            layer.blit(img2, (58, 26 - img.get_height() // 2))
            surf.blit(layer, rect.topleft)


def currency_bar(surf, assets, x_right, y, coins, gems, extra=None):
    """Top-right coin & gem counters. Returns left x."""
    x = x_right
    items = [("gem", gems, S.GEM_COLOR), ("coin", coins, S.COIN_COLOR)]
    if extra:
        items.insert(0, extra)
    for icon, val, col in items:
        t = assets.text(fmt_int(val), 26, (255, 255, 255))
        w = t.get_width() + 62
        rect = pygame.Rect(x - w, y, w, 44)
        pygame.draw.rect(surf, (12, 14, 30), rect, border_radius=22)
        pygame.draw.rect(surf, shade(col, 0.8), rect, 2, border_radius=22)
        surf.blit(assets.icon(icon, 34, col), (rect.x + 6, rect.y + 5))
        surf.blit(t, (rect.x + 46, rect.centery - t.get_height() // 2))
        x = rect.x - 10
    return x


# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------
class HUD:
    def __init__(self, assets):
        self.assets = assets
        self.pause_rect = pygame.Rect(S.SCREEN_W - 78, 14, 62, 62)
        self.coin_pulse = 0.0
        self.zone_banner = None  # (text, timer)
        self.start_buttons = []  # [(rect, key, icon, label, count)]

    def pulse_coin(self):
        self.coin_pulse = 1.0

    def show_zone(self, name):
        self.zone_banner = [name, 3.0]

    def update(self, dt):
        self.coin_pulse = max(0.0, self.coin_pulse - dt * 4)
        if self.zone_banner:
            self.zone_banner[1] -= dt
            if self.zone_banner[1] <= 0:
                self.zone_banner = None

    @property
    def coin_target(self):
        return (S.SCREEN_W - 210, 110)

    def draw(self, surf, sess):
        a = self.assets
        # --- score panel (top-left)
        panel(surf, (14, 14, 300, 96), (14, 16, 34), radius=18, shadow=False, alpha=170)
        score = a.text(fmt_int(sess.score), 46, (255, 255, 255), shadow=True)
        surf.blit(score, (30, 18))
        dist = a.text(f"{fmt_int(sess.distance)} m", 24, S.UI_TEXT_DIM)
        surf.blit(dist, (32, 72))
        # multiplier badge
        mult = sess.multiplier
        mcol = S.UI_ACCENT if mult < 2 else (255, 120, 60) if mult < 4 else (255, 60, 160)
        mrect = pygame.Rect(232, 26, 74, 46)
        pygame.draw.rect(surf, shade(mcol, 0.5), mrect.move(0, 3), border_radius=14)
        pygame.draw.rect(surf, mcol, mrect, border_radius=14)
        mt = a.text(f"x{mult:g}" if mult < 10 else f"x{int(mult)}", 28, (30, 20, 10))
        blit_center(surf, mt, mrect.center)
        # combo meter
        if sess.combo > 0:
            frac = sess.combo_timer / S.COMBO_DECAY_TIME
            progress_bar(surf, (32, 100, 200, 8), frac, (255, 120, 60), radius=4)
            ct = a.text(f"COMBO {sess.combo}", 18, (255, 170, 90))
            surf.blit(ct, (238, 92))

        # --- currencies (top-right, left of pause)
        s = 1.0 + self.coin_pulse * 0.25
        coins = a.text(fmt_int(sess.coins), int(30 * s) if s > 1.01 else 30, (255, 255, 255), shadow=True)
        rect = pygame.Rect(0, 0, 150, 50)
        rect.topright = (S.SCREEN_W - 92, 18)
        panel(surf, rect, (14, 16, 34), radius=25, shadow=False, alpha=170)
        surf.blit(a.icon("coin", 38), (rect.x + 6, rect.y + 6))
        surf.blit(coins, (rect.x + 50, rect.centery - coins.get_height() // 2))
        y = 76
        if sess.gems_run:
            g = a.text(str(sess.gems_run), 26, (255, 255, 255))
            surf.blit(a.icon("gem", 30), (S.SCREEN_W - 236, y))
            surf.blit(g, (S.SCREEN_W - 200, y + 2))
            y += 36
        if sess.event and sess.tokens_run:
            col = sess.event["currency"]["color"]
            t = a.text(str(sess.tokens_run), 26, (255, 255, 255))
            surf.blit(a.icon("token", 30, col), (S.SCREEN_W - 236, y))
            surf.blit(t, (S.SCREEN_W - 200, y + 2))

        # --- pause button
        pygame.draw.circle(surf, (14, 16, 34), self.pause_rect.center, 31)
        pygame.draw.circle(surf, (255, 255, 255), self.pause_rect.center, 31, 3)
        blit_center(surf, a.icon("pause", 30, (255, 255, 255)), self.pause_rect.center)

        # --- power-up timers (left side)
        y = 140
        for definition, remaining, duration in sess.powerups.hud_entries():
            col = definition.get("color", (255, 255, 255))
            rect = pygame.Rect(18, y, 210, 50)
            panel(surf, rect, (14, 16, 34), radius=14, shadow=False, alpha=170)
            surf.blit(a.icon(definition.get("icon", "star"), 38, col), (rect.x + 6, rect.y + 6))
            name = a.text(definition.get("name", ""), 18, (255, 255, 255))
            surf.blit(name, (rect.x + 52, rect.y + 6))
            frac = remaining / max(0.01, duration)
            blink = remaining < 2.0 and int(remaining * 6) % 2 == 0
            progress_bar(surf, (rect.x + 52, rect.y + 30, 146, 10), frac, (255, 255, 255) if blink else col, radius=5)
            y += 58

        # --- start-of-run consumable buttons
        for rect, key, icon, label, count in self.start_buttons:
            panel(surf, rect, (14, 16, 34), radius=18, shadow=False, alpha=190)
            pygame.draw.rect(surf, S.UI_ACCENT, rect, 2, border_radius=18)
            surf.blit(a.icon(icon, 44, S.UI_ACCENT), (rect.x + 8, rect.y + 8))
            surf.blit(a.text(label, 18, (255, 255, 255)), (rect.x + 60, rect.y + 8))
            surf.blit(a.text(f"[{key}] x{count}", 18, S.UI_TEXT_DIM), (rect.x + 60, rect.y + 32))

        # --- zone banner
        if self.zone_banner:
            name, t = self.zone_banner
            k = min(1.0, (3.0 - t) * 4, t * 2)
            img = a.text(name.upper(), 44, (255, 255, 255), shadow=True)
            sub = a.text("NOW ENTERING", 20, S.UI_ACCENT)
            w = max(img.get_width(), sub.get_width()) + 80
            layer = pygame.Surface((w, 100), pygame.SRCALPHA)
            pygame.draw.rect(layer, (10, 12, 28, int(190 * k)), (0, 0, w, 100), border_radius=20)
            img2 = img.copy()
            img2.set_alpha(int(255 * k))
            sub2 = sub.copy()
            sub2.set_alpha(int(255 * k))
            layer.blit(sub2, (w // 2 - sub.get_width() // 2, 10))
            layer.blit(img2, (w // 2 - img.get_width() // 2, 36))
            surf.blit(layer, (S.SCREEN_W // 2 - w // 2, 130 - int((1 - k) * 30)))
