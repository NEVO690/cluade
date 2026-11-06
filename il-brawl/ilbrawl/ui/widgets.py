"""Reusable UI widgets: buttons, sliders, toggles, selectors, tabs, scroll panels, inputs, dialogs."""
import math

import pygame

from ilbrawl.audio import audio
from ilbrawl.ui import text, theme


class Widget:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.visible = True
        self.enabled = True
        self.hover = False

    def handle_event(self, e):
        return False

    def update(self, dt, mouse_pos):
        self.hover = bool(mouse_pos) and self.visible and self.rect.collidepoint(mouse_pos)

    def draw(self, surf):
        pass


class Label(Widget):
    def __init__(self, rect, label, size=24, color=theme.WHITE, align="start", valign="middle", outline=2):
        super().__init__(rect)
        self.label, self.size, self.color, self.align, self.valign, self.outline = label, size, color, align, valign, outline

    def draw(self, surf):
        a = text.resolve_align(self.align)
        x = {"left": self.rect.x, "right": self.rect.right, "center": self.rect.centerx}[a]
        y = {"top": self.rect.y, "middle": self.rect.centery, "bottom": self.rect.bottom}[self.valign]
        text.draw(surf, self.label() if callable(self.label) else self.label, (x, y), self.size, self.color,
                  a, self.valign, outline=self.outline, max_width=self.rect.w)


class Button(Widget):
    def __init__(self, rect, label="", on_click=None, color=theme.BLUE, text_size=26, icon=None,
                 radius=16, enabled=True, sound="click", badge=None, sublabel=None, text_color=theme.WHITE,
                 icon_side="start"):
        super().__init__(rect)
        self.label = label
        self.on_click = on_click
        self.color = color
        self.text_size = text_size
        self.icon = icon
        self.radius = radius
        self.enabled = enabled
        self.sound = sound
        self.badge = badge          # callable -> int/bool, draws a red notification dot
        self.sublabel = sublabel
        self.text_color = text_color
        self.icon_side = icon_side
        self.pressed = False
        self.anim = 0.0
        self.selected = False

    def handle_event(self, e):
        if not self.visible:
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.pressed = True
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            was = self.pressed
            self.pressed = False
            if was and self.rect.collidepoint(e.pos):
                if self.enabled:
                    if self.sound:
                        audio.play(self.sound)
                    if self.on_click:
                        self.on_click()
                else:
                    audio.play("deny")
                return True
        return False

    def update(self, dt, mouse_pos):
        super().update(dt, mouse_pos)
        target = 1.0 if self.hover else 0.0
        self.anim += (target - self.anim) * min(1.0, dt * 12)

    def draw(self, surf):
        if not self.visible:
            return
        grow = int(self.anim * 6)
        r = self.rect.inflate(grow, grow)
        color = self.color
        if self.selected:
            pygame.draw.rect(surf, theme.YELLOW, r.inflate(14, 14), 4, border_radius=self.radius + 6)
        body = theme.draw_button_shape(surf, r, color, self.pressed and self.hover, self.hover,
                                       self.radius, not self.enabled)
        label = self.label() if callable(self.label) else self.label
        cx, cy = body.centerx, body.centery
        if self.icon and label:
            isz = min(body.h - 14, 44)
            rtl = text.resolve_align("start") == "right"
            on_left = (self.icon_side == "start") != rtl
            ix = body.x + 10 + isz // 2 if on_left else body.right - 10 - isz // 2
            self.icon(surf, pygame.Rect(ix - isz // 2, cy - isz // 2, isz, isz))
            avail = body.w - isz - 30
            tx = (body.x + isz + 20 + body.right - 10) // 2 if on_left else (body.x + 10 + body.right - isz - 20) // 2
            self._draw_label(surf, label, tx, cy, avail)
        elif self.icon:
            isz = min(body.w, body.h) - 12
            self.icon(surf, pygame.Rect(cx - isz // 2, cy - isz // 2, isz, isz))
        else:
            self._draw_label(surf, label, cx, cy, body.w - 16)
        if self.badge:
            b = self.badge()
            if b:
                bx = r.right - 6 if text.resolve_align("start") == "left" else r.x + 6
                pygame.draw.circle(surf, theme.INK, (bx, r.y + 6), 13)
                pygame.draw.circle(surf, theme.RED, (bx, r.y + 6), 11)
                if isinstance(b, int) and not isinstance(b, bool):
                    text.draw(surf, str(b), (bx, r.y + 6), 14, align="center", valign="middle", outline=0)

    def _draw_label(self, surf, label, cx, cy, avail):
        if self.sublabel:
            sub = self.sublabel() if callable(self.sublabel) else self.sublabel
            text.draw(surf, label, (cx, cy - 10), self.text_size, self.text_color, "center", "middle", max_width=avail)
            text.draw(surf, sub, (cx, cy + 16), max(12, self.text_size - 10), theme.WHITE, "center", "middle",
                      outline=2, max_width=avail)
        else:
            text.draw(surf, label, (cx, cy), self.text_size, self.text_color, "center", "middle", max_width=avail)


class Slider(Widget):
    def __init__(self, rect, value=0.5, on_change=None, color=theme.YELLOW, rtl=False):
        super().__init__(rect)
        self.value = value
        self.on_change = on_change
        self.color = color
        self.dragging = False
        self.rtl = rtl

    def _set_from(self, x):
        t = (x - self.rect.x) / max(1, self.rect.w)
        if self.rtl:
            t = 1 - t
        v = max(0.0, min(1.0, t))
        if abs(v - self.value) > 1e-4:
            self.value = v
            if self.on_change:
                self.on_change(v)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.inflate(16, 24).collidepoint(e.pos):
            self.dragging = True
            self._set_from(e.pos[0])
            return True
        if e.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from(e.pos[0])
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.dragging:
            self.dragging = False
            audio.play("click")
            return True
        return False

    def draw(self, surf):
        r = self.rect
        track = pygame.Rect(r.x, r.centery - 7, r.w, 14)
        pygame.draw.rect(surf, theme.INK, track.inflate(4, 4), border_radius=9)
        pygame.draw.rect(surf, theme.darken(theme.PANEL, 0.3), track, border_radius=7)
        fw = int(track.w * self.value)
        fill = pygame.Rect(track.right - fw if self.rtl else track.x, track.y, fw, track.h)
        if fw > 0:
            pygame.draw.rect(surf, self.color, fill, border_radius=7)
        kx = track.right - fw if self.rtl else track.x + fw
        pygame.draw.circle(surf, theme.INK, (kx, track.centery + 2), 15)
        pygame.draw.circle(surf, theme.WHITE, (kx, track.centery), 13)
        pygame.draw.circle(surf, self.color, (kx, track.centery), 7)
        txt_x = r.x - 16 if self.rtl else r.right + 16
        text.draw(surf, "%d%%" % round(self.value * 100), (txt_x, r.centery), 20,
                  align="right" if self.rtl else "left", valign="middle", rtl=False)


class Toggle(Widget):
    def __init__(self, rect, value=False, on_change=None, rtl=False):
        super().__init__(rect)
        self.value = value
        self.on_change = on_change
        self.anim = 1.0 if value else 0.0
        self.rtl = rtl

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.rect.collidepoint(e.pos):
            self.value = not self.value
            audio.play("click")
            if self.on_change:
                self.on_change(self.value)
            return True
        return False

    def update(self, dt, mouse_pos):
        super().update(dt, mouse_pos)
        self.anim += ((1.0 if self.value else 0.0) - self.anim) * min(1, dt * 14)

    def draw(self, surf):
        r = self.rect
        col = theme.lerp_color(theme.GREY, theme.GREEN, self.anim)
        pygame.draw.rect(surf, theme.INK, r.inflate(4, 4), border_radius=r.h // 2 + 2)
        pygame.draw.rect(surf, col, r, border_radius=r.h // 2)
        t = self.anim if not self.rtl else 1 - self.anim
        kx = int(r.x + r.h // 2 + t * (r.w - r.h))
        pygame.draw.circle(surf, theme.WHITE, (kx, r.centery), r.h // 2 - 4)


class Selector(Widget):
    """< value > cycling selector."""

    def __init__(self, rect, options, index=0, on_change=None, color=theme.PURPLE):
        super().__init__(rect)
        self.options = options      # list of display strings
        self.index = index
        self.on_change = on_change
        self.color = color
        h = self.rect.h
        self.left = pygame.Rect(self.rect.x, self.rect.y, h, h)
        self.right = pygame.Rect(self.rect.right - h, self.rect.y, h, h)

    def _step(self, d):
        self.index = (self.index + d) % len(self.options)
        audio.play("click")
        if self.on_change:
            self.on_change(self.index)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self.left.collidepoint(e.pos):
                self._step(-1)
                return True
            if self.right.collidepoint(e.pos):
                self._step(1)
                return True
            if self.rect.collidepoint(e.pos):
                self._step(1)
                return True
        return False

    def draw(self, surf):
        mid = pygame.Rect(self.left.right + 6, self.rect.y, self.right.x - self.left.right - 12, self.rect.h)
        theme.draw_panel(surf, mid, theme.darken(theme.PANEL, 0.2), theme.PANEL_BORDER, 12, False, 2)
        text.draw(surf, self.options[self.index], mid.center, 21, align="center", valign="middle", max_width=mid.w - 10)
        for rr, d in ((self.left, -1), (self.right, 1)):
            body = theme.draw_button_shape(surf, rr.inflate(-4, -4), self.color, radius=10)
            cx, cy = body.center
            s = body.h // 4
            pts = [(cx + s * d, cy), (cx - s * d * 0.6, cy - s), (cx - s * d * 0.6, cy + s)]
            pygame.draw.polygon(surf, theme.WHITE, pts)


class TabBar(Widget):
    def __init__(self, rect, labels, index=0, on_change=None, rtl=False, color=theme.PURPLE):
        super().__init__(rect)
        self.labels = labels
        self.index = index
        self.on_change = on_change
        self.rtl = rtl
        self.color = color
        self.badges = [None] * len(labels)

    def tab_rect(self, i):
        n = len(self.labels)
        w = self.rect.w // n
        pos = (n - 1 - i) if self.rtl else i
        return pygame.Rect(self.rect.x + pos * w + 3, self.rect.y, w - 6, self.rect.h)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            for i in range(len(self.labels)):
                if self.tab_rect(i).collidepoint(e.pos):
                    if i != self.index:
                        self.index = i
                        audio.play("tab")
                        if self.on_change:
                            self.on_change(i)
                    return True
        return False

    def draw(self, surf):
        for i, lab in enumerate(self.labels):
            r = self.tab_rect(i)
            sel = i == self.index
            col = self.color if sel else theme.darken(theme.PANEL_LIGHT, 0.1)
            body = theme.draw_button_shape(surf, r, col, pressed=sel, radius=12)
            text.draw(surf, lab, body.center, 20, theme.WHITE if sel else theme.TEXT_DIM, "center", "middle",
                      max_width=body.w - 10)
            b = self.badges[i]
            if b and b():
                pygame.draw.circle(surf, theme.INK, (r.right - 6, r.y + 4), 9)
                pygame.draw.circle(surf, theme.RED, (r.right - 6, r.y + 4), 7)


class ScrollPanel(Widget):
    """Clipped, scrollable container. Children use content coordinates (0,0 = panel top-left)."""

    def __init__(self, rect, horizontal=False):
        super().__init__(rect)
        self.children = []
        self.offset = 0.0
        self.target = 0.0
        self.content_size = 0
        self.horizontal = horizontal
        self.drag_start = None
        self.dragged = False
        self.background = None
        self.draw_content = None   # optional callback(surface, offset) for custom drawing under children

    def add(self, w):
        self.children.append(w)
        return w

    def clear(self):
        self.children = []

    def max_offset(self):
        view = self.rect.w if self.horizontal else self.rect.h
        return max(0, self.content_size - view)

    def scroll_to(self, v, instant=False):
        self.target = max(0, min(self.max_offset(), v))
        if instant:
            self.offset = self.target

    def _local(self, pos):
        if self.horizontal:
            return (pos[0] - self.rect.x + self.offset, pos[1] - self.rect.y)
        return (pos[0] - self.rect.x, pos[1] - self.rect.y + self.offset)

    def handle_event(self, e):
        if not self.visible:
            return False
        if e.type == pygame.MOUSEWHEEL:
            mp = getattr(e, "vpos", None)
            if mp and self.rect.collidepoint(mp):
                self.target = max(0, min(self.max_offset(), self.target - e.y * 60))
                return True
            return False
        if hasattr(e, "pos"):
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
                self.drag_start = (e.pos, self.target)
                self.dragged = False
            if e.type == pygame.MOUSEMOTION and self.drag_start and getattr(e, "buttons", (0,))[0]:
                d = (e.pos[0] - self.drag_start[0][0]) if self.horizontal else (e.pos[1] - self.drag_start[0][1])
                if abs(d) > 8:
                    self.dragged = True
                if self.dragged:
                    self.target = max(0, min(self.max_offset(), self.drag_start[1] - d))
                    self.offset = self.target
                    return True
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                was_drag = self.dragged
                self.drag_start = None
                self.dragged = False
                if was_drag:
                    for c in self.children:
                        if hasattr(c, "pressed"):
                            c.pressed = False
                    return True
            inside = self.rect.collidepoint(e.pos)
            if not inside and e.type != pygame.MOUSEBUTTONUP:
                return False
            d = dict(e.__dict__)
            d["pos"] = self._local(e.pos) if inside else (-9999, -9999)
            le = pygame.event.Event(e.type, d)
            for c in reversed(self.children):
                if c.visible and c.handle_event(le):
                    return True
            return inside and e.type == pygame.MOUSEBUTTONDOWN
        return False

    def update(self, dt, mouse_pos):
        super().update(dt, mouse_pos)
        self.target = max(0, min(self.max_offset(), self.target))
        self.offset += (self.target - self.offset) * min(1, dt * 14)
        local = self._local(mouse_pos) if (mouse_pos and self.rect.collidepoint(mouse_pos)) else None
        for c in self.children:
            c.update(dt, local)

    def draw(self, surf):
        if not self.visible:
            return
        canvas = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        off = int(self.offset)
        if self.draw_content:
            self.draw_content(canvas, off)
        for c in self.children:
            if not c.visible:
                continue
            orig = c.rect
            c.rect = orig.move(-off, 0) if self.horizontal else orig.move(0, -off)
            vis = c.rect.colliderect(pygame.Rect(-60, -60, self.rect.w + 120, self.rect.h + 120))
            if vis:
                c.draw(canvas)
            c.rect = orig
        surf.blit(canvas, self.rect.topleft)
        # scrollbar
        if self.max_offset() > 0:
            if self.horizontal:
                frac = self.rect.w / self.content_size
                bw = max(40, int(self.rect.w * frac))
                bx = self.rect.x + int((self.rect.w - bw) * (self.offset / self.max_offset()))
                pygame.draw.rect(surf, theme.PANEL_BORDER, (bx, self.rect.bottom - 6, bw, 5), border_radius=3)
            else:
                frac = self.rect.h / self.content_size
                bh = max(40, int(self.rect.h * frac))
                by = self.rect.y + int((self.rect.h - bh) * (self.offset / self.max_offset()))
                sx = self.rect.x + 2 if text.resolve_align("start") == "right" else self.rect.right - 7
                pygame.draw.rect(surf, theme.PANEL_BORDER, (sx, by, 5, bh), border_radius=3)


class TextInput(Widget):
    def __init__(self, rect, value="", max_len=16, on_submit=None, size=24):
        super().__init__(rect)
        self.value = value
        self.max_len = max_len
        self.on_submit = on_submit
        self.active = False
        self.size = size
        self.t = 0.0
        self.placeholder = ""

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            was = self.active
            self.active = self.rect.collidepoint(e.pos)
            if self.active:
                pygame.key.start_text_input()
            elif was and self.on_submit:
                self.on_submit(self.value)
            return self.active
        if not self.active:
            return False
        if e.type == pygame.TEXTINPUT:
            for ch in e.text:
                if len(self.value) < self.max_len and ch.isprintable():
                    self.value += ch
            return True
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.active = False
                if self.on_submit:
                    self.on_submit(self.value)
            elif e.key == pygame.K_ESCAPE:
                self.active = False
            return True
        return False

    def update(self, dt, mouse_pos):
        super().update(dt, mouse_pos)
        self.t += dt

    def draw(self, surf):
        col = theme.lighten(theme.PANEL, 0.1) if self.active else theme.darken(theme.PANEL, 0.2)
        theme.draw_panel(surf, self.rect, col, theme.YELLOW if self.active else theme.PANEL_BORDER, 12, False, 3)
        shown = self.value + ("|" if self.active and int(self.t * 2) % 2 == 0 else "")
        a = text.resolve_align("start")
        x = self.rect.x + 14 if a == "left" else self.rect.right - 14
        if not self.value and not self.active and self.placeholder:
            text.draw(surf, self.placeholder, (x, self.rect.centery), self.size, theme.GREY, a, "middle", outline=0)
            return
        text.draw(surf, shown, (x, self.rect.centery), self.size, align=a, valign="middle", max_width=self.rect.w - 24)


class Dialog:
    """Modal dialog with title, message and buttons [(label, color, callback)]."""

    def __init__(self, title, message, buttons, width=560, height=300, draw_extra=None):
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (640, 360)
        self.title = title
        self.message = message
        self.draw_extra = draw_extra
        self.closed = False
        self.buttons = []
        n = len(buttons)
        bw = min(220, (width - 40 - (n - 1) * 20) // max(1, n))
        total = n * bw + (n - 1) * 20
        x0 = self.rect.centerx - total // 2
        rtl = text.resolve_align("start") == "right"
        order = list(reversed(buttons)) if rtl else buttons
        for i, (label, color, cb) in enumerate(order):
            def make(cb=cb):
                def f():
                    self.closed = True
                    if cb:
                        cb()
                return f
            self.buttons.append(Button((x0 + i * (bw + 20), self.rect.bottom - 86, bw, 60), label, make(), color, 24))
        self.anim = 0.0

    def handle_event(self, e):
        for b in self.buttons:
            if b.handle_event(e):
                return True
        return True  # modal swallows everything

    def update(self, dt, mouse_pos):
        self.anim = min(1.0, self.anim + dt * 6)
        for b in self.buttons:
            b.update(dt, mouse_pos)

    def draw(self, surf):
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((10, 6, 30, int(170 * self.anim)))
        surf.blit(shade, (0, 0))
        s = 0.85 + 0.15 * math.sin(self.anim * math.pi / 2)
        r = self.rect.inflate(int(self.rect.w * (s - 1)), int(self.rect.h * (s - 1)))
        theme.draw_panel(surf, r, theme.PANEL, theme.YELLOW, 22)
        text.draw(surf, self.title, (r.centerx, r.y + 22), 32, theme.YELLOW, "center", max_width=r.w - 40)
        if self.draw_extra:
            self.draw_extra(surf, r)
        text.draw_wrapped(surf, self.message, (r.x + 30, r.y + 76, r.w - 60, r.h - 170), 22, theme.WHITE,
                          "center", False, outline=0)
        for b in self.buttons:
            b.draw(surf)


class ProgressBar:
    @staticmethod
    def draw(surf, rect, frac, color=theme.GREEN, bg=None, rtl=False, label=None, label_size=16):
        rect = pygame.Rect(rect)
        frac = max(0.0, min(1.0, frac))
        pygame.draw.rect(surf, theme.INK, rect.inflate(4, 4), border_radius=rect.h // 2 + 2)
        pygame.draw.rect(surf, bg or theme.darken(theme.PANEL, 0.35), rect, border_radius=rect.h // 2)
        fw = int(rect.w * frac)
        if fw > 0:
            fr = pygame.Rect(rect.right - fw if rtl else rect.x, rect.y, fw, rect.h)
            pygame.draw.rect(surf, color, fr, border_radius=rect.h // 2)
            hl = pygame.Rect(fr.x + 3, fr.y + 2, max(0, fr.w - 6), max(2, rect.h // 3))
            if hl.w > 4:
                pygame.draw.rect(surf, theme.lighten(color, 0.35), hl, border_radius=hl.h // 2)
        if label is not None:
            text.draw(surf, label, rect.center, label_size, align="center", valign="middle")


class Group(Widget):
    """A widget with custom drawing and child widgets placed relative to its rect.

    Works inside ScrollPanel because children are re-positioned from the group's rect on
    every event, update and draw.
    """

    def __init__(self, rect, draw_fn=None):
        super().__init__(rect)
        self.draw_fn = draw_fn
        self.children = []   # [widget, dx, dy]

    def add(self, widget, dx, dy):
        self.children.append([widget, dx, dy])
        return widget

    def _sync(self):
        for w, dx, dy in self.children:
            w.rect.topleft = (self.rect.x + dx, self.rect.y + dy)

    def handle_event(self, e):
        self._sync()
        for w, _, _ in reversed(self.children):
            if w.visible and w.handle_event(e):
                return True
        return False

    def update(self, dt, mouse_pos):
        super().update(dt, mouse_pos)
        self._sync()
        for w, _, _ in self.children:
            w.update(dt, mouse_pos)

    def draw(self, surf):
        self._sync()
        if self.draw_fn:
            self.draw_fn(surf, self.rect)
        for w, _, _ in self.children:
            if w.visible:
                w.draw(surf)
