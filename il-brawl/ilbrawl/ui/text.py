"""Text rendering with RTL support, outlines, auto-fit and wrapping (cached)."""
import pygame

from ilbrawl.engine import assets
from ilbrawl.localization import bidi, i18n
from ilbrawl.ui import theme

_cache = {}
_CACHE_LIMIT = 1500


def _rtl():
    inst = i18n.get()
    return bool(inst and inst.rtl)


def render(text, size, color=theme.WHITE, bold=True, outline=2, outline_color=theme.INK, rtl=None):
    text = str(text)
    if rtl is None:
        rtl = _rtl()
    key = (text, size, tuple(color), bold, outline, tuple(outline_color), rtl)
    s = _cache.get(key)
    if s is not None:
        return s
    font = assets.get().font(size, bold)
    visual = bidi.to_visual(text, rtl)
    glyphs = font.render(visual, True, color)
    if outline > 0 and glyphs.get_width() > 0:
        w, h = glyphs.get_width() + outline * 2, glyphs.get_height() + outline * 2 + max(1, outline // 2)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        ol = font.render(visual, True, outline_color)
        offsets = [(dx, dy) for dx in range(-outline, outline + 1) for dy in range(-outline, outline + 1)
                   if dx * dx + dy * dy <= outline * outline + 1]
        for dx, dy in offsets:
            s.blit(ol, (outline + dx, outline + dy + max(1, outline // 2)))
        s.blit(glyphs, (outline, outline))
    else:
        s = glyphs
    if len(_cache) > _CACHE_LIMIT:
        _cache.clear()
    _cache[key] = s
    return s


def resolve_align(align):
    rtl = _rtl()
    if align == "start":
        return "right" if rtl else "left"
    if align == "end":
        return "left" if rtl else "right"
    return align


def draw(surf, text, pos, size=24, color=theme.WHITE, align="left", valign="top", bold=True,
         outline=2, outline_color=theme.INK, max_width=None, rtl=None):
    """Draw text anchored at pos. align: left/center/right/start/end."""
    s = render(text, size, color, bold, outline, outline_color, rtl)
    if max_width and s.get_width() > max_width and size > 11:
        # shrink to fit long translations instead of overflowing
        new_size = max(11, int(size * max_width / s.get_width()))
        while new_size > 11:
            s = render(text, new_size, color, bold, outline, outline_color, rtl)
            if s.get_width() <= max_width:
                break
            new_size -= 1
    a = resolve_align(align)
    x, y = pos
    if a == "center":
        x -= s.get_width() // 2
    elif a == "right":
        x -= s.get_width()
    if valign == "middle":
        y -= s.get_height() // 2
    elif valign == "bottom":
        y -= s.get_height()
    surf.blit(s, (int(x), int(y)))
    return pygame.Rect(int(x), int(y), s.get_width(), s.get_height())


def wrap(text, size, width, bold=False):
    font = assets.get().font(size, bold)
    lines = []
    for para in str(text).split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip() if cur else w
            if font.size(trial)[0] <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def draw_wrapped(surf, text, rect, size=20, color=theme.WHITE, align="start", bold=False, outline=0,
                 line_gap=4, max_lines=None):
    rect = pygame.Rect(rect)
    lines = wrap(text, size, rect.w - 4, bold)
    if max_lines:
        lines = lines[:max_lines]
    y = rect.y
    a = resolve_align(align)
    for line in lines:
        if a == "right":
            x = rect.right - 2
        elif a == "center":
            x = rect.centerx
        else:
            x = rect.x + 2
        r = draw(surf, line, (x, y), size, color, a, "top", bold, outline)
        y += r.h + line_gap
    return y - rect.y


def size(text, size, bold=True):
    return assets.get().font(size, bold).size(str(text))
