"""The runner: lane switching, jumping, sliding, flying, animation and drawing."""
import math

import pygame

from . import settings as S
from . import model3d
from .render import make_radial
from .utils import approach, clamp

JUMP_BUFFER = 0.16
COYOTE_TIME = 0.1


class Player:
    def __init__(self, look, board=None, jump_bonus=0.0, assets=None):
        self.look = look
        self.board = board
        self.jump_bonus = jump_bonus
        self.assets = assets
        self.reset()
        self._shadow = pygame.transform.smoothscale(make_radial(48, (0, 0, 0), 150), (96, 30))
        self._shield = None
        self._jetpack = model3d.jetpack_part()
        self._board_cache = {}

    def reset(self):
        self.lane = 1
        self.prev_lane = 1
        self.x = 0.0
        self.y = 0.0
        self.prev_y = 0.0
        self.vy = 0.0
        self.z = 0.0
        self.prev_z = 0.0
        self.on_ground = True
        self.ground_y = 0.0
        self.standing_on = None
        self.air_time = 0.0
        self.slide_timer = 0.0
        self.fast_fall = False
        self.jump_buffer = 0.0
        self.pending_jump_mult = 1.0
        self.flying = False
        self.flight_height = 0.0
        self.board_active = False
        self.dead = False
        self.t = 0.0
        self.anim_phase = 0.0
        self.blink = False
        self.events = []
        self.emote_text = ""
        self.emote_timer = 0.0

    # ------------------------------------------------------------------
    @property
    def sliding(self):
        return self.slide_timer > 0

    @property
    def height(self):
        return S.PLAYER_SLIDE_HEIGHT if self.sliding else S.PLAYER_HEIGHT

    def box(self):
        return (self.x - S.PLAYER_HALF_W, self.x + S.PLAYER_HALF_W, self.y, self.y + self.height,
                self.z - S.PLAYER_HALF_D, self.z + S.PLAYER_HALF_D)

    # ------------------------------------------------------------------
    # Input actions
    # ------------------------------------------------------------------
    def move(self, direction):
        if self.dead:
            return False
        new = self.lane + direction
        if 0 <= new < S.LANE_COUNT:
            self.prev_lane = self.lane
            self.lane = new
            self.events.append("lane")
            return True
        self.events.append("edge")
        return False

    def bounce_back(self):
        """Undo a lane switch after bumping into the side of something."""
        self.lane, self.prev_lane = self.prev_lane, self.lane

    def jump(self, jump_mult=1.0):
        if self.dead or self.flying:
            return False
        if self.on_ground or self.air_time < COYOTE_TIME and self.vy <= 0:
            self.vy = S.JUMP_VELOCITY * jump_mult * (1.0 + self.jump_bonus)
            self.on_ground = False
            self.air_time = COYOTE_TIME
            self.slide_timer = 0.0
            self.fast_fall = False
            self.jump_buffer = 0.0
            self.events.append("jump")
            return True
        self.jump_buffer = JUMP_BUFFER
        self.pending_jump_mult = jump_mult
        return False

    def slide(self):
        if self.dead or self.flying:
            return False
        if not self.on_ground:
            self.fast_fall = True
            self.vy = min(self.vy, -6.0)
        self.slide_timer = S.SLIDE_TIME
        self.jump_buffer = 0.0
        self.events.append("slide")
        return True

    def start_flight(self, height):
        self.flying = True
        self.flight_height = height
        self.slide_timer = 0.0
        self.on_ground = False

    def end_flight(self):
        self.flying = False
        self.vy = 0.0

    def die(self):
        self.dead = True
        self.flying = False
        self.slide_timer = 0.0
        self.vy = 7.0
        self.on_ground = False

    def revive(self):
        self.dead = False
        self.vy = 0.0
        self.y = max(self.y, self.ground_y)

    def show_emote(self, text, duration=2.2):
        if text:
            self.emote_text = text
            self.emote_timer = duration

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def update(self, dt, speed, world):
        self.t += dt
        self.prev_z = self.z
        self.prev_y = self.y
        if self.emote_timer > 0:
            self.emote_timer -= dt
        if self.dead:
            self.vy -= S.GRAVITY * dt
            self.y = max(self.ground_y, self.y + self.vy * dt)
            self.z += speed * dt
            return
        self.z += speed * dt
        self.x = approach(self.x, S.LANE_X[self.lane], S.LANE_SWITCH_SPEED * dt)
        if self.slide_timer > 0:
            self.slide_timer = max(0.0, self.slide_timer - dt)
        self.anim_phase += dt * (6.0 + speed * 0.32)

        if self.flying:
            self.y += (self.flight_height - self.y) * min(1.0, dt * 3.0)
            self.vy = 0.0
            self.on_ground = False
            self.standing_on = None
            return

        g = S.FAST_FALL_GRAVITY if self.fast_fall else S.GRAVITY
        self.vy -= g * dt
        self.y += self.vy * dt
        ground, surface = world.ground_height(self.x, self.z, self.prev_y)
        self.ground_y = ground
        if self.y <= ground:
            was_air = not self.on_ground
            self.y = ground
            self.vy = 0.0
            self.on_ground = True
            self.air_time = 0.0
            self.fast_fall = False
            if was_air:
                self.events.append("land")
                if surface is not None and surface.kind in ("train", "car") and surface is not self.standing_on:
                    self.events.append("roof")
            self.standing_on = surface
            if self.jump_buffer > 0:
                self.jump(self.pending_jump_mult)
        else:
            if self.on_ground and self.y - ground > 0.05:
                self.on_ground = False
            if not self.on_ground:
                self.air_time += dt
                self.standing_on = None
        if self.jump_buffer > 0:
            self.jump_buffer -= dt

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def pose(self):
        if self.dead:
            return "fall"
        if self.sliding:
            return "slide"
        if not self.on_ground:
            return "jump"
        return "run"

    def _board_part(self, lift):
        key = (self.board.get("id"), lift)
        part = self._board_cache.get(key)
        if part is None:
            part = model3d.board_part(self.board)
            part.verts = [(x, y - lift, z) for x, y, z in part.verts]
            self._board_cache[key] = part
        return part

    def queue_draw(self, r, shielded=False, jet=False, magnet=False):
        r.queue(self.z + 0.02, self._draw, r, shielded, jet, magnet)

    def _draw(self, r, shielded, jet, magnet):
        cam = r.cam
        dz = self.z - cam.z
        if dz < S.NEAR_PLANE:
            return
        s = cam.focal / dz
        surf = r.surface
        # shadow on the surface below
        gx, gy = r.proj(self.x, self.ground_y, self.z)
        height_above = max(0.0, self.y - self.ground_y)
        sw = int(0.55 * s / (1 + height_above * 0.25))
        if sw > 2:
            shadow = r.scaled("shadow", self._shadow, sw * 0.62)
            surf.blit(shadow, (gx - shadow.get_width() / 2, gy - shadow.get_height() / 2))
        if self.blink and int(self.t * 14) % 2 == 0:
            return
        board_lift = 0.0
        extra = []
        if self.board_active and self.board and not jet:
            hover = self.board.get("style") == "hover"
            board_lift = 0.24 if hover else 0.13
            extra.append(self._board_part(board_lift))
            if self.board.get("style") in ("neon", "hover", "cyber") and r.glow_enabled:
                r.draw_glow(self.x, self.y + 0.05, self.z, 0.9, self.board["colors"]["glow"])
        if jet:
            extra.append(self._jetpack)
        lean = clamp((S.LANE_X[self.lane] - self.x) / S.LANE_WIDTH, -1, 1)
        frames = self.assets.sprite_frames(self.look.get("id", ""), self.pose()) if self.assets else []
        if frames:
            fx, fy = r.proj(self.x, self.y + board_lift, self.z)
            idx = int(self.anim_phase / math.pi * 2) % len(frames)
            img = r.scaled(("pl", self.look.get("id"), self.pose(), idx), frames[idx], S.PLAYER_HEIGHT * s)
            surf.blit(img, (fx - img.get_width() / 2, fy - img.get_height()))
        else:
            pose = self.pose()
            if pose == "jump" and self.flying:
                pose = "run"
            model3d.draw_in_world(r, self.look, pose, self.anim_phase, self.t, self.x, self.y + board_lift, self.z,
                                  lean, extra)
        if jet:
            # exhaust flames under the jetpack nozzles
            for sx in (-0.1, 0.1):
                fl = 0.3 + 0.15 * math.sin(self.t * 40 + sx * 30)
                ax, ay = r.proj(self.x + sx, self.y + 0.9, self.z - 0.27)
                bx, by = r.proj(self.x + sx, self.y + 0.9 - fl, self.z - 0.35)
                w = max(2, int(0.06 * s))
                pygame.draw.polygon(surf, (255, 170, 30), [(ax - w, ay), (ax + w, ay), (bx, by)])
                pygame.draw.polygon(surf, (255, 240, 160), [(ax - w * 0.5, ay), (ax + w * 0.5, ay), (bx, (ay + by) / 2)])
        if magnet:
            mx, my = r.proj(self.x, self.y + 1.0, self.z)
            rr = int(0.9 * s * (1 + 0.1 * math.sin(self.t * 10)))
            if rr > 3:
                pygame.draw.circle(surf, (255, 90, 90), (int(mx), int(my)), rr, max(1, rr // 14))
        if shielded:
            cx, cy = r.proj(self.x, self.y + self.height * 0.55, self.z)
            rad = int(self.height * 0.75 * s)
            if rad > 4:
                if self._shield is None:
                    self._shield = pygame.Surface((256, 256), pygame.SRCALPHA)
                    pygame.draw.circle(self._shield, (90, 180, 255, 60), (128, 128), 126)
                    pygame.draw.circle(self._shield, (170, 220, 255, 170), (128, 128), 126, 6)
                    pygame.draw.ellipse(self._shield, (255, 255, 255, 90), (60, 30, 70, 40))
                img = r.scaled("shield", self._shield, rad * 2)
                surf.blit(img, (cx - img.get_width() / 2, cy - img.get_height() / 2))
        if self.emote_timer > 0 and self.emote_text and self.assets:
            ex, ey = r.proj(self.x, self.y + 2.4, self.z)
            txt = self.assets.text(self.emote_text, 26, (30, 30, 40))
            pad = 10
            rect = pygame.Rect(0, 0, txt.get_width() + pad * 2, txt.get_height() + pad)
            rect.midbottom = (ex, ey)
            pygame.draw.rect(surf, (255, 255, 255), rect, border_radius=12)
            pygame.draw.polygon(surf, (255, 255, 255), [(ex - 8, rect.bottom - 1), (ex + 8, rect.bottom - 1), (ex, rect.bottom + 10)])
            surf.blit(txt, (rect.x + pad, rect.y + pad // 2))
