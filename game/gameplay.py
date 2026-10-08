"""A single run (GameSession) and the scene that hosts it (GameScene)."""
import math
import random

import pygame

from . import settings as S
from .camera import Camera
from .characters import build_look
from .collectibles import COIN, GEM, TOKEN, POWERUP, CollectibleRenderer
from .effects import ParticleSystem, ScreenParticles, FloatingTexts, SpeedLines, Weather, Flash, RAINBOW
from .obstacles import LOW, HIGH, BLOCK, TRAIN, RAMP, CAR
from .player import Player
from .powerups import PowerUpManager
from .render import Renderer
from .scenery import zone_colors
from .ui import HUD, Button, panel, blit_center, progress_bar
from .utils import clamp, lerp_color, fmt_int
from .world import World, default_speed

RUN_STATS = ("coins", "gems", "tokens", "distance", "score", "jumps", "slides", "lane_switches", "jump_over",
             "slide_under", "trains_landed", "powerups", "boards_used", "powerup_jet", "top_speed")


class GameSession:
    """All state of one run: player, world, score, power-ups and rules."""

    def __init__(self, app):
        self.app = app
        gd, save, eco = app.data, app.save, app.economy
        self.quality = app.settings.quality
        self.char = gd.character(save["character"])
        ab = self.char["ability"]
        self.ability = (ab.get("type", "none"), float(ab.get("value", 0)))
        look = build_look(gd, save["character"], save["outfit"])
        self.board = gd.item(save["board"])
        self.trail = gd.item(save["trail"]) or {"style": "none"}
        self.effect = gd.item(save["effect"]) or {"style": "sparkle", "color": (255, 230, 120)}
        self.emote = gd.item(save["emote"]) or {"text": ""}
        self.event = app.events.active()
        jump_bonus = self.ability[1] if self.ability[0] == "jump_bonus" else 0.0
        self.player = Player(look, self.board, jump_bonus, app.assets)
        dur_bonus = self.ability[1] if self.ability[0] == "powerup_duration" else 0.0
        self.powerups = PowerUpManager(gd, eco, dur_bonus)
        self.world = World(gd, self.quality, app.progression.unlocked_zone_ids(), app.assets, event=self.event,
                           seed=random.randrange(1 << 30), speed_fn=default_speed, sprites=app.sprites)
        self.camera = Camera()
        self.particles = ParticleSystem(self.quality["particles"])
        self.score = 0.0
        self.coins = 0
        self.gems_run = 0
        self.tokens_run = 0
        self.distance = 0.0
        self.combo = 0
        self.combo_timer = 0.0
        self.time = 0.0
        self.state = "running"        # running | dead | over
        self.dead_timer = 0.0
        self.stumble_timer = 0.0
        self.bump_cooldown = 0.0
        self.invuln = 0.0
        self.revives = 0
        self.zone_id = None
        self.stats = {k: 0 for k in RUN_STATS}
        self.booster = 0.0
        self.level_mult = 1.0 + 0.25 * (app.progression.level // 5)
        self.events_out = []        # (kind, data) consumed by the scene for UI feedback
        self.result = None
        self.speed = 0.0
        self.start_window = 6.0     # seconds during which head start / booster can be used
        app.missions.begin_run()
        # character abilities that trigger at start
        if self.ability[0] == "magnet_start":
            self.powerups.activate("magnet", self, duration=max(1.0, self.ability[1]))
        elif self.ability[0] == "shield_start":
            self.powerups.activate("shield", self, duration=30.0)
        self.player.show_emote(self.emote.get("text", ""))
        self.world.update(0, 0, self.camera.z, self.draw_distance)
        self.camera.follow(self.player.x, self.player.y, self.player.z, 0, snap=True)

    # ------------------------------------------------------------------
    @property
    def draw_distance(self):
        return self.quality["draw_distance"]

    @property
    def combo_mult(self):
        return min(S.COMBO_MAX_MULT, 1.0 + 0.5 * (self.combo // S.COMBO_STEP))

    @property
    def multiplier(self):
        m = (self.level_mult + self.booster) * self.combo_mult * self.powerups.score_mult
        if self.ability[0] == "score_bonus":
            m *= 1.0 + self.ability[1]
        return round(m * 2) / 2

    def current_speed(self):
        base = default_speed(self.player.z)
        ramp = min(1.0, 0.35 + self.time / 1.2)
        return base * ramp * self.powerups.speed_mult

    def emit(self, kind, data=None):
        self.events_out.append((kind, data))

    def record(self, stat, amount=1, run_value=None):
        if stat in self.stats and stat not in ("distance", "score", "top_speed"):
            self.stats[stat] += amount
        self.app.missions.record(stat, amount, run_value)

    def add_combo(self, n):
        before = self.combo_mult
        self.combo += n
        self.combo_timer = S.COMBO_DECAY_TIME
        if self.combo_mult > before:
            self.emit("combo", self.combo_mult)
            self.app.missions.record("combo", 0, self.combo_mult)

    def grant_invulnerability(self, seconds):
        self.invuln = max(self.invuln, seconds)

    # ------------------------------------------------------------------
    # Actions (called by the scene's input handling)
    # ------------------------------------------------------------------
    def act(self, action):
        if self.state != "running":
            return
        p = self.player
        if action == "left":
            if p.move(-1):
                self.record("lane_switches")
                self.app.audio.play("whoosh", 0.6)
        elif action == "right":
            if p.move(1):
                self.record("lane_switches")
                self.app.audio.play("whoosh", 0.6)
        elif action == "jump":
            if p.jump(self.powerups.jump_mult):
                self.record("jumps")
                self.app.audio.play("jump", 0.8)
        elif action == "slide":
            if p.slide():
                self.record("slides")
                self.app.audio.play("slide", 0.7)
        elif action == "board":
            self.use_board()
        elif action == "head_start":
            self.use_head_start()
        elif action == "booster":
            self.use_booster()

    def use_board(self):
        if self.powerups.has("board") or not self.board:
            return False
        if not self.app.economy.use_consumable("board_charge"):
            self.app.audio.play("error")
            self.emit("toast", "No Board Charges - buy them in the Shop")
            return False
        definition = {"id": "board", "name": self.board["name"], "effect": "board", "icon": "board",
                      "color": self.board["colors"]["glow"], "params": {"perk": self.board["perk"]}}
        self.powerups.activate("board", self, duration=30.0, definition=definition)
        self.record("boards_used")
        self.app.audio.play("board")
        return True

    def use_head_start(self):
        if self.time > self.start_window or not self.app.economy.use_consumable("head_start"):
            return False
        self.powerups.activate("jet", self, duration=12.0)
        self.app.audio.play("jet")
        self.start_window = 0
        return True

    def use_booster(self):
        if self.time > self.start_window or self.booster or not self.app.economy.use_consumable("score_booster"):
            return False
        self.booster = 1.0
        self.app.audio.play("powerup")
        self.emit("toast", "Score Booster: +1 multiplier!")
        return True

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def update(self, dt):
        dt = min(dt, S.MAX_FRAME_DT)
        self.camera.update(dt)
        self.particles.update(dt)
        if self.state == "dead":
            self.dead_timer -= dt
            self.player.update(dt, 0.0, self.world)
            self.camera.follow(self.player.x, self.player.y * 0.3, self.player.z, dt)
            if self.dead_timer <= 0:
                self.state = "over"
                self.emit("dead")
            return
        if self.state != "running":
            return
        self.time += dt
        steps = max(1, int(math.ceil(dt / S.PHYSICS_STEP)))
        h = dt / steps
        for _ in range(steps):
            self._step(h)
            if self.state != "running":
                break
        self._frame_update(dt)

    def _step(self, h):
        p = self.player
        self.speed = self.current_speed()
        prev_z = p.z
        p.update(h, self.speed, self.world)
        for m in self.world.movers:
            m.update(h)
        moved = p.z - prev_z
        self.distance = p.z
        self.score += moved * 2.0 * self.multiplier
        if self.invuln > 0:
            self.invuln -= h
        if self.bump_cooldown > 0:
            self.bump_cooldown -= h
        if self.stumble_timer > 0:
            self.stumble_timer -= h
        self._collide()
        self._handle_player_events()

    def _handle_player_events(self):
        p = self.player
        for ev in p.events:
            if ev == "land":
                self.app.audio.play("land", 0.5)
                self.particles.burst(p.x, p.y + 0.05, p.z, 5, (200, 200, 200), speed=2.5, life=0.35, size=0.08, gravity=-4)
            elif ev == "roof":
                self.record("trains_landed")
                self.add_combo(3)
            elif ev == "edge":
                self.camera.shake(3, 0.12)
        p.events.clear()

    def _collide(self):
        p = self.player
        if p.dead:
            return
        px0, px1, py0, py1, pz0, pz1 = p.box()
        flying = p.flying
        invincible = self.powerups.invincible
        for ob in self.world.obstacles_near(pz0 - 0.5, pz1 + 0.5):
            if abs(ob.x - p.x) >= S.LANE_HALF + S.PLAYER_HALF_W:
                continue
            if ob.z1 <= pz0 or ob.z0 >= pz1:
                continue
            top = ob.top_at(p.z)
            if ob.kind == RAMP:
                # ramps are walkable; only their sides (when entering mid-ramp from below) bump
                if py0 >= top - S.STEP_HEIGHT or ob is p.standing_on:
                    continue
            if py0 >= top - 0.05 or py1 <= ob.y0 or ob is p.standing_on:
                continue
            if p.on_ground and ob.walkable and top - py0 <= S.STEP_HEIGHT:
                continue  # stepping up (ramp -> train roof, roof -> next roof)
            if flying:
                continue
            front = (p.prev_z + S.PLAYER_HALF_D) <= ob.prev_z0 + 0.03 or ob.kind in (LOW, HIGH)
            if invincible:
                self._smash(ob)
                continue
            if self.invuln > 0:
                continue
            if not front and ob.lane == p.lane and abs(p.x - S.LANE_X[p.lane]) < 0.05 and ob.walkable:
                # we are inside the obstacle (e.g. invincibility just ran out mid-train): pop onto the roof
                p.y = top
                p.vy = 0.0
                p.on_ground = True
                p.standing_on = ob
                continue
            if front:
                self._crash(ob)
            else:
                self._side_bump(ob)
            if self.state != "running":
                return

    def _smash(self, ob):
        if ob.kind in (TRAIN, RAMP):
            return  # trains are too big to smash - pass through while invincible
        ob.alive = False
        self.app.audio.play("smash", 0.8)
        self.particles.burst(ob.x, 1.0, ob.z0, 18, ob.color, speed=7, life=0.7, size=0.2, gravity=-14, kind="square")
        self.camera.shake(5, 0.2)
        self.add_combo(2)
        self.score += 50 * self.multiplier

    def _crash(self, ob):
        used = self.powerups.consume_hit_absorber(self)
        if used:
            self.app.audio.play("shield_break")
            self.emit("flash", (120, 200, 255))
            self.emit("toast", "Shield saved you!" if used == "shield" else "Board saved you!")
            self.grant_invulnerability(S.INVULN_AFTER_SAVE)
            if ob.kind not in (TRAIN, RAMP):
                ob.alive = False
                self.particles.burst(ob.x, 1.0, ob.z0, 16, ob.color, speed=6, life=0.6, size=0.2, gravity=-14, kind="square")
            self.camera.shake(8, 0.3)
            return
        self._die()

    def _side_bump(self, ob):
        if self.bump_cooldown > 0:
            return
        self.bump_cooldown = 0.4
        self.player.bounce_back()
        self.camera.shake(7, 0.25)
        self.combo = 0
        self.particles.burst(self.player.x, 1.2, self.player.z, 8, (255, 255, 255), speed=3, life=0.4, size=0.1)
        if self.stumble_timer > 0:
            self.app.audio.play("hit")
            self._crash(ob)
        else:
            self.app.audio.play("stumble")
            self.stumble_timer = S.STUMBLE_WINDOW
            self.emit("toast", "Careful! Another bump ends the run")

    def _die(self):
        self.state = "dead"
        self.dead_timer = 1.2
        self.player.die()
        self.powerups.clear(self)
        self.app.audio.play("hit")
        self.camera.shake(16, 0.5)
        self.emit("flash", (255, 60, 60))
        self.particles.burst(self.player.x, 1.0, self.player.z + 0.5, 24, (255, 230, 120), speed=6, life=0.8, size=0.14,
                             gravity=-12, kind="star")

    def _frame_update(self, dt):
        p = self.player
        world = self.world
        world.update(dt, p.z, self.camera.z, self.draw_distance, move_movers=False)
        self.powerups.update(dt, self)
        self.player.blink = self.invuln > 0 and not self.powerups.invincible
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0
        self.camera.follow(p.x, p.y, p.z, dt)
        self.camera.set_speed_factor((self.speed - S.START_SPEED) / (S.MAX_SPEED - S.START_SPEED))
        self.stats["top_speed"] = max(self.stats["top_speed"], default_speed(p.z))
        self.app.missions.record("distance", self.distance - getattr(self, "_last_dist", 0.0), self.distance)
        self._last_dist = self.distance
        self.app.missions.record("score", self.score - getattr(self, "_last_score", 0.0), self.score)
        self._last_score = self.score
        self._collect(dt)
        self._passed_obstacles()
        self._zone_check()
        self._trail(dt)

    def _collect(self, dt):
        p = self.player
        radius = self.powerups.magnet_radius
        look = max(2.0, radius + 1.0)
        mid_y = p.y + p.height * 0.5
        for c in list(self.world.collectibles_near(p.z - 2.0, p.z + look)):
            if radius > 0 and not c.magnet and c.kind != POWERUP:
                if (c.x - p.x) ** 2 + (c.z - p.z) ** 2 < radius * radius and abs(c.y - mid_y) < 6:
                    c.magnet = True
            if c.magnet:
                c.update_magnet(p.x, mid_y, p.z, dt)
            if abs(c.x - p.x) < 0.95 and abs(c.z - p.z) < 1.0 and p.y - 0.5 < c.y < p.y + p.height + 0.6:
                self._pickup(c)

    def _pickup(self, c):
        c.alive = False
        if c.kind == COIN:
            self.coins += 1
            self.record("coins")
            self.score += S.COIN_SCORE * self.multiplier
            self.add_combo(1)
            self.app.audio.play("coin", 0.55)
            self._pickup_fx(c)
            self.emit("coin", (c.x, c.y, c.z))
        elif c.kind == GEM:
            self.gems_run += 1
            self.record("gems")
            self.score += S.GEM_SCORE * self.multiplier
            self.add_combo(5)
            self.app.audio.play("gem")
            self.particles.burst(c.x, c.y, c.z, 14, S.GEM_COLOR, speed=4, life=0.6, size=0.12, kind="star")
            self.emit("text", ("+1 GEM", S.GEM_COLOR))
        elif c.kind == TOKEN:
            self.tokens_run += 1
            self.record("tokens")
            self.add_combo(2)
            self.app.audio.play("token")
            col = self.event["currency"]["color"] if self.event else (255, 200, 60)
            self.particles.burst(c.x, c.y, c.z, 12, col, speed=4, life=0.6, size=0.12, kind="star")
        elif c.kind == POWERUP:
            pu = self.app.data.powerup_by_id.get(c.value)
            if pu and self.powerups.activate(c.value, self):
                self.record("powerups")
                self.record(f"powerup_{c.value}")
                self.add_combo(4)
                self.app.audio.play(pu.get("sound", "powerup"))
                self.emit("flash", pu["color"])
                self.emit("text", (pu["name"].upper(), pu["color"]))
                self.particles.burst(c.x, c.y, c.z, 20, pu["color"], speed=5, life=0.7, size=0.14, kind="ring")

    def _pickup_fx(self, c):
        style = self.effect.get("style", "sparkle")
        col = self.effect.get("color", (255, 230, 120))
        if style == "burst":
            self.particles.burst(c.x, c.y, c.z, 6, col, speed=4, life=0.4, size=0.1, gravity=0, kind="star")
        elif style == "ring":
            self.particles.emit(c.x, c.y, c.z, 0, 0, 0, 0.35, 0.6, col, 0, "ring")
        elif style == "confetti":
            self.particles.burst(c.x, c.y, c.z, 6, "rainbow", speed=3.5, life=0.6, size=0.08, gravity=-6, kind="square")
        else:
            self.particles.burst(c.x, c.y, c.z, 4, col, speed=2.5, life=0.35, size=0.08, gravity=0)

    def _passed_obstacles(self):
        p = self.player
        for ob in self.world.obstacles_near(p.z - 6, p.z - S.PLAYER_HALF_D):
            if ob.counted or ob.z1 > p.z - S.PLAYER_HALF_D:
                continue
            ob.counted = True
            same_lane = abs(ob.x - p.x) < S.LANE_HALF
            if same_lane and ob.kind == LOW and not p.flying:
                self.record("jump_over")
                self.add_combo(3)
            elif same_lane and ob.kind == HIGH and not p.flying:
                self.record("slide_under")
                self.add_combo(3)
            elif same_lane and ob.kind in (CAR, BLOCK) and not p.flying:
                self.record("jump_over")
                self.add_combo(4)
            elif abs(ob.x - p.x) < S.LANE_WIDTH + 0.3 and ob.kind in (TRAIN, BLOCK) and not p.flying:
                self.add_combo(1)  # near miss

    def _zone_check(self):
        zid = self.world.schedule.zone_id_at(self.player.z + 10)
        if zid != self.zone_id:
            self.zone_id = zid
            zone = self.app.data.zone_by_id.get(zid)
            self.app.audio.play_music(zid)
            seen = self.app.save["zones_seen"]
            if zid not in seen:
                seen.append(zid)
                self.app.save.mark_dirty()
            self.app.missions.record(f"zone_{zid}", 1)
            self.emit("zone", zone["name"] if zone else zid)

    def _trail(self, dt):
        style = self.trail.get("style", "none")
        p = self.player
        if p.dead:
            return
        # particles inherit most of the runner's forward speed so they trail a few metres
        # behind instead of flying into the camera
        fz = self.speed * 0.8
        emit = self.particles.emit
        if self.powerups.has("jet"):
            for _ in range(2):
                emit(p.x + random.uniform(-0.2, 0.2), p.y + 0.7, p.z - 0.3, random.uniform(-0.4, 0.4),
                     -3, fz, 0.3, 0.12, random.choice([(255, 170, 40), (255, 90, 30), (255, 230, 120)]), 0, "dot")
        if self.powerups.has("speed"):
            emit(p.x + random.uniform(-0.6, 0.6), p.y + random.uniform(0.2, 1.6), p.z - 0.5, 0, 0, fz,
                 0.25, 0.08, (255, 240, 120), 0, "streak")
        if p.board_active and self.board and self.board.get("style") in ("neon", "cyber", "hover"):
            emit(p.x, p.y + 0.1, p.z - 0.6, 0, 0, fz, 0.4, 0.08, self.board["colors"]["glow"], 0, "dot")
        if style == "none":
            return
        col = self.trail.get("color", (255, 255, 255))
        x, y, z = p.x + random.uniform(-0.15, 0.15), p.y + 0.15, p.z - 0.4
        if style == "sparks":
            emit(x, y, z, random.uniform(-1.5, 1.5), random.uniform(1, 3), fz, 0.4, 0.05,
                 random.choice([col, (255, 255, 200)]), -9, "dot")
        elif style == "bubbles":
            if random.random() < 0.5:
                emit(x, y + 0.5, z, random.uniform(-0.4, 0.4), random.uniform(0.5, 1.5), fz, 0.7, 0.1, col, 0, "bubble")
        elif style == "streak":
            emit(p.x, y + 0.6, z, 0, 0, fz, 0.35, 0.12, col, 0, "dot")
        elif style == "rainbow":
            emit(x, y + 0.5, z, 0, 0, fz, 0.45, 0.09, RAINBOW[int(self.time * 12) % len(RAINBOW)], 0, "square")
        elif style == "stars":
            if random.random() < 0.6:
                emit(x, y + random.uniform(0, 1.2), z, 0, 0.3, fz, 0.6, 0.09, col, 0, "star")
        elif style == "leaves":
            if random.random() < 0.5:
                emit(x, y + 0.8, z, random.uniform(-1, 1), 0.5, fz, 0.8, 0.09,
                     random.choice([(230, 120, 30), (200, 70, 20), (240, 180, 40)]), -2, "square")

    # ------------------------------------------------------------------
    # Revive / finish
    # ------------------------------------------------------------------
    def can_revive(self):
        return self.revives < 2 and self.app.economy.consumable("revive_key") > 0

    def revive(self):
        if not self.app.economy.use_consumable("revive_key"):
            return False
        self.revives += 1
        p = self.player
        self.world.clear_ahead(p.z, ahead=60)
        p.revive()
        p.y = 0.0
        p.ground_y = 0.0
        self.state = "running"
        self.grant_invulnerability(3.0)
        self.stumble_timer = 0
        self.app.audio.play("powerup")
        self.app.audio.play_music(self.zone_id or "menu")
        return True

    def finalize(self):
        """Bank the run's rewards. Safe to call once."""
        if self.result is not None:
            return self.result
        app = self.app
        eco, save, prog = app.economy, app.save, app.progression
        coin_bonus = self.ability[1] if self.ability[0] == "coin_bonus" else 0.0
        coins_earned = int(round(self.coins * (1 + coin_bonus)))
        eco.add("coins", coins_earned)
        eco.add("gems", self.gems_run)
        if self.event and self.tokens_run:
            app.events.add_tokens(self.event, self.tokens_run)
        xp_bonus = self.ability[1] if self.ability[0] == "xp_bonus" else 0.0
        xp = int((self.distance / 8 + self.coins / 3 + self.score / 500 + 10) * (1 + xp_bonus))
        app.missions.record("runs", 1)
        old_level = prog.level
        prog.add_xp(xp)
        st = self.stats
        st["distance"] = int(self.distance)
        st["score"] = int(self.score)
        for k in ("coins", "gems", "tokens", "distance", "score", "jumps", "slides", "lane_switches", "jump_over",
                  "slide_under", "trains_landed", "powerups", "boards_used", "powerup_jet"):
            if st[k]:
                save.stat_add(k, st[k])
        save.stat_add("runs", 1)
        save.stat_max("top_speed", round(st["top_speed"], 1))
        save["tutorial_done"] = True
        new_best = self.score > save["best_score"]
        if new_best:
            save["best_score"] = int(self.score)
        if self.distance > save["best_distance"]:
            save["best_distance"] = int(self.distance)
        season_pts = 0
        season = app.season.current()
        if season:
            season_pts = app.season.run_points(season, self.distance, self.coins, len(app.missions.completed_this_run))
            app.season.add_points(season_pts)
        new_ach = app.achievements.check()
        save.save()
        self.result = {
            "score": int(self.score), "distance": int(self.distance), "coins": coins_earned, "gems": self.gems_run,
            "tokens": self.tokens_run, "xp": xp, "best": save["best_score"], "new_best": new_best,
            "missions": [m.desc for m, _ in app.missions.completed_this_run],
            "achievements": [a["name"] for a in new_ach], "level_up": prog.level > old_level, "level": prog.level,
            "season_points": season_pts,
        }
        return self.result


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
class GameScene:
    def __init__(self, app):
        self.app = app
        self.session = None
        self.renderer = Renderer(app.screen, Camera())
        self.crender = CollectibleRenderer(app.assets, app.data)
        self.sky = app.sky
        self.hud = HUD(app.assets)
        self.screen_particles = ScreenParticles()
        self.texts = FloatingTexts()
        self.speed_lines = SpeedLines()
        self.weather = Weather()
        self.flash = Flash()
        self.mode = "play"   # play | paused | countdown | revive | over
        self.countdown = 0.0
        self.revive_timer = 0.0
        self.buttons = []
        self.debug = False
        self._touch_start = None
        self._last_tap = 0.0
        self._fps_hist = []

    # ------------------------------------------------------------------
    def enter(self, **kw):
        if kw.get("resume") and self.session is not None:
            self.mode = "paused"
            self._build_pause()
            return
        self.start_new()

    def start_new(self):
        self.session = GameSession(self.app)
        self.renderer.cam = self.session.camera
        self.mode = "play"
        self.texts.items.clear()
        self.screen_particles.items.clear()
        ev = self.session.event
        w = ev["theme"].get("weather", "") if ev else ""
        self.weather.set(w, self.app.settings.quality.get("weather", 60))
        self._build_start_buttons()
        self.app.audio.play("go")

    def _build_start_buttons(self):
        eco = self.app.economy
        btns = []
        y = S.SCREEN_H - 90
        x = S.SCREEN_W - 250
        for cid, key, icon, label in (("head_start", "H", "head_start", "HEAD START"),
                                      ("score_booster", "M", "booster", "BOOSTER")):
            n = eco.consumable(cid)
            if n > 0:
                btns.append((pygame.Rect(x, y, 230, 64), key, icon, label, n))
                y -= 74
        n = eco.consumable("board_charge")
        btns.append((pygame.Rect(S.SCREEN_W - 250, y, 230, 64), "B", "board", "BOARD", n))
        self.hud.start_buttons = btns

    def _build_pause(self):
        cx = S.SCREEN_W // 2
        self.buttons = [
            Button((cx - 160, 250, 320, 70), "RESUME", self._resume, "good", icon="play"),
            Button((cx - 160, 335, 320, 70), "RESTART", self._restart, "secondary", icon="retry"),
            Button((cx - 160, 420, 320, 70), "SETTINGS", lambda: self.app.change_scene("settings", back="game"), "dark", icon="gear"),
            Button((cx - 160, 505, 320, 70), "QUIT", self._quit, "danger", icon="home"),
        ]

    def _build_over(self):
        cx = S.SCREEN_W // 2
        self.buttons = [
            Button((cx - 330, 600, 300, 76), "RETRY", self._restart, "good", icon="retry", size=34),
            Button((cx + 30, 600, 300, 76), "HOME", self._quit, "secondary", icon="home", size=34),
        ]

    def _build_revive(self):
        cx = S.SCREEN_W // 2
        n = self.app.economy.consumable("revive_key")
        self.buttons = [
            Button((cx - 180, 420, 360, 80), f"SAVE ME ({n} key{'s' if n != 1 else ''})", self._do_revive, "good", icon="key", size=30),
            Button((cx - 120, 520, 240, 60), "SKIP", self._skip_revive, "dark", size=26),
        ]

    def _resume(self):
        self.mode = "countdown"
        self.countdown = 3.0
        self.buttons = []
        self.app.audio.play("countdown")

    def _restart(self):
        if self.session and self.session.result is None and self.session.state != "over":
            # quitting mid-run still banks what was collected
            self.session.finalize()
        self.start_new()

    def _quit(self):
        if self.session and self.session.result is None:
            self.session.finalize()
        self.app.audio.pause_music(False)
        self.app.change_scene("menu")

    def _do_revive(self):
        if self.session.revive():
            self.mode = "countdown"
            self.countdown = 2.0
            self.buttons = []

    def _skip_revive(self):
        self._game_over()

    def _game_over(self):
        self.session.finalize()
        self.mode = "over"
        self._build_over()
        self.app.audio.play("game_over")
        self.app.audio.play_music("menu")
        res = self.session.result
        if res["new_best"]:
            self.screen_particles.burst(S.SCREEN_W // 2, 160, 60, "rainbow", speed=500, life=1.4, size=6, gravity=500)
        # the results panel lists missions, achievements and level-ups itself
        self.app.toasts.items.clear()
        self.level_lines = []
        for lvl, lines in self.app.progression.pending_level_ups:
            self.level_lines.extend(lines)
        self.app.progression.pending_level_ups.clear()
        if res["level_up"]:
            self.app.audio.play("level_up")

    def pause(self):
        if self.mode in ("play", "countdown") and self.session and self.session.state == "running":
            self.mode = "paused"
            self._build_pause()
            self.app.audio.pause_music(True)
            self.app.audio.play("back")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle(self, event):
        app = self.app
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F3:
            self.debug = not self.debug
            return
        if event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWMINIMIZED):
            self.pause()
            return
        if self.mode in ("paused", "over", "revive"):
            for b in self.buttons:
                if b.handle(event, app):
                    return
            if event.type == pygame.KEYDOWN:
                if self.mode == "paused" and app.key_action(event.key) == "pause":
                    self._resume()
                elif self.mode == "over" and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._restart()
                elif self.mode == "revive" and event.key == pygame.K_RETURN:
                    self._do_revive()
            return
        if self.mode != "play":
            return
        sess = self.session
        if event.type == pygame.KEYDOWN:
            action = app.key_action(event.key)
            if action == "pause":
                self.pause()
            elif action:
                sess.act(action)
            elif event.key == pygame.K_h:
                if sess.use_head_start():
                    self.hud.start_buttons = []
            elif event.key == pygame.K_m:
                if sess.use_booster():
                    self._build_start_buttons()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.hud.pause_rect.collidepoint(event.pos):
                self.pause()
                return
            for rect, key, *_ in self.hud.start_buttons:
                if rect.collidepoint(event.pos):
                    if key == "H" and sess.use_head_start():
                        self.hud.start_buttons = []
                    elif key == "M" and sess.use_booster():
                        self._build_start_buttons()
                    elif key == "B":
                        sess.act("board")
                    return
            self._touch_start = (event.pos, pygame.time.get_ticks())
        elif event.type == pygame.MOUSEMOTION and self._touch_start:
            self._check_swipe(event.pos, final=False)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._touch_start:
            if not self._check_swipe(event.pos, final=True):
                now = pygame.time.get_ticks()
                if now - self._last_tap < 320:
                    sess.act("board")  # double tap
                    self._last_tap = 0
                else:
                    self._last_tap = now
            self._touch_start = None

    def _check_swipe(self, pos, final):
        start, _ = self._touch_start
        dx = pos[0] - start[0]
        dy = pos[1] - start[1]
        th = self.app.settings["swipe_threshold"]
        if max(abs(dx), abs(dy)) < th:
            return False
        if abs(dx) > abs(dy):
            self.session.act("right" if dx > 0 else "left")
        else:
            self.session.act("slide" if dy > 0 else "jump")
        self._touch_start = None
        return True

    # ------------------------------------------------------------------
    def update(self, dt):
        sess = self.session
        self.hud.update(dt)
        self.screen_particles.update(dt)
        self.texts.update(dt)
        self.flash.update(dt)
        for b in self.buttons:
            b.update(dt)
        if self.mode == "countdown":
            prev = int(self.countdown)
            self.countdown -= dt
            if int(self.countdown) != prev and self.countdown > 0:
                self.app.audio.play("countdown")
            if self.countdown <= 0:
                self.mode = "play"
                self.app.audio.pause_music(False)
                self.app.audio.play("go")
        if self.mode == "play":
            sess.update(dt)
            if sess.time > sess.start_window and self.hud.start_buttons:
                self.hud.start_buttons = [b for b in self.hud.start_buttons if b[1] == "B"]
                if sess.time > sess.start_window + 4:
                    self.hud.start_buttons = []
        elif self.mode in ("over", "revive"):
            sess.camera.update(dt)
            sess.particles.update(dt)
        if self.mode == "revive":
            self.revive_timer -= dt
            if self.revive_timer <= 0:
                self._game_over()
        self.weather.update(dt if self.mode == "play" else dt * 0.3,
                            (sess.speed - S.START_SPEED) / (S.MAX_SPEED - S.START_SPEED) if self.mode == "play" else 0)
        self._process_session_events()

    def _process_session_events(self):
        sess = self.session
        for kind, data in sess.events_out:
            if kind == "coin":
                proj = sess.camera.project(*data)
                if proj:
                    self.screen_particles.emit(proj[0], proj[1], 0, 0, 0.5, 5, S.COIN_COLOR, target=self.hud.coin_target)
                self.hud.pulse_coin()
            elif kind == "text":
                text, col = data
                self.texts.add(text, S.SCREEN_W // 2, S.SCREEN_H * 0.32, col, 40, 1.3, -40)
            elif kind == "combo":
                self.texts.add(f"COMBO x{data:g}!", S.SCREEN_W // 2, S.SCREEN_H * 0.42, (255, 150, 60), 34, 1.0, -50)
            elif kind == "flash":
                self.flash.trigger(data, 0.3)
            elif kind == "toast":
                self.app.toasts.push(data, "star", S.UI_ACCENT_2, 2.2)
            elif kind == "zone":
                self.hud.show_zone(data)
            elif kind == "dead":
                if sess.can_revive():
                    self.mode = "revive"
                    self.revive_timer = 5.0
                    self._build_revive()
                else:
                    self._game_over()
        sess.events_out.clear()
        for m, lines in self.app.missions.completed_this_run[getattr(self, "_missions_seen", 0):]:
            self.app.toasts.push(f"Mission complete: {m.desc}", "mission", S.UI_GOOD, 3.2)
            self.app.audio.play("mission")
        self._missions_seen = len(self.app.missions.completed_this_run)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surf):
        sess = self.session
        cam = sess.camera
        r = self.renderer
        r.surface = surf
        world = sess.world
        q = sess.quality
        zone_a, zone_b, t = world.schedule.zone_at(cam.z + 30)
        colors = zone_colors(zone_a, zone_b, t)
        r.begin(colors["fog"], q["draw_distance"], q.get("glow", True))
        self.sky.draw(surf, cam, zone_a, zone_b, t)
        world.draw_ground(r, cam)
        world.draw(r, self.crender, cam.z, passed_z=sess.player.z - S.PLAYER_HALF_D)
        self.crender.time = sess.time
        if sess.event:
            self.crender.token_color = sess.event["currency"]["color"]
        pw = sess.powerups
        sess.particles.queue_draw(r)
        r.flush()
        # The runner is drawn after the world: nothing visible can be in front of it (obstacles it has
        # passed are not drawn), while long trains/ramps it stands on would otherwise win the depth sort.
        sess.player._draw(r, pw.has("shield"), pw.has("jet"), pw.magnet_radius > 0 and pw.has("magnet"))
        if sess.event:
            th = sess.event["theme"]
            mult = lerp_color((255, 255, 255), th["tint"], th["tint_strength"])
            surf.fill(mult, special_flags=pygame.BLEND_MULT)
        if world.in_tunnel(sess.player.z):
            surf.fill((205, 200, 215), special_flags=pygame.BLEND_MULT)
        if self.mode == "play":
            f = (sess.speed - 24) / (S.MAX_SPEED * 1.45 - 24)
            if pw.has("speed") or pw.has("jet"):
                f = max(f, 0.8)
            self.speed_lines.draw(surf, cam.hx, cam.hy + 40, clamp(f, 0, 1), 1 / 60)
        self.weather.draw(surf)
        if self.mode in ("play", "countdown", "paused"):
            self.hud.draw(surf, sess)
        self.screen_particles.draw(surf)
        self.texts.draw(surf, self.app.assets)
        self.flash.draw(surf)
        if self.mode == "play" and not self.app.save["tutorial_done"] and 3.0 < sess.time < 12:
            self._draw_tutorial(surf, sess.time - 3.0)
        if sess.stumble_timer > 0 and self.mode == "play":
            k = sess.stumble_timer / S.STUMBLE_WINDOW
            pygame.draw.rect(surf, (255, 80, 60), (0, 0, S.SCREEN_W, S.SCREEN_H), max(1, int(10 * k)))
        if self.mode == "paused":
            self._draw_pause(surf)
        elif self.mode == "countdown":
            n = int(math.ceil(self.countdown))
            img = self.app.assets.text(str(n), 120, (255, 255, 255), shadow=True)
            k = self.countdown - int(self.countdown)
            img = pygame.transform.rotozoom(img, 0, 0.8 + 0.5 * k)
            blit_center(surf, img, (S.SCREEN_W // 2, S.SCREEN_H // 2 - 40))
        elif self.mode == "revive":
            self._draw_revive(surf)
        elif self.mode == "over":
            self._draw_over(surf)
        if self.debug:
            self._draw_debug(surf)

    def _draw_tutorial(self, surf, t):
        a = self.app.assets
        k = min(1.0, t * 2, (9 - t) * 2)
        lines = [("<  >", "A / D / arrows / swipe", "Change lane"),
                 ("^", "W / Up / Space / swipe up", "Jump"),
                 ("v", "S / Down / swipe down", "Slide")]
        w, h = 540, 30 + 40 * len(lines)
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(layer, (10, 12, 30, int(200 * k)), (0, 0, w, h), border_radius=20)
        pygame.draw.rect(layer, (*S.UI_ACCENT, int(255 * k)), (0, 0, w, h), 3, border_radius=20)
        for i, (sym, keys, label) in enumerate(lines):
            y = 16 + i * 40
            for img, x in ((a.text(sym, 24, S.UI_ACCENT), 20), (a.text(label, 21, (255, 255, 255)), 88),
                           (a.text(keys, 18, S.UI_TEXT_DIM), 248)):
                img = img.copy()
                img.set_alpha(int(255 * k))
                layer.blit(img, (x, y))
        surf.blit(layer, (S.SCREEN_W - w - 20, 150))

    def _dim(self, surf, alpha=150):
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        layer.fill((8, 10, 24, alpha))
        surf.blit(layer, (0, 0))

    def _draw_pause(self, surf):
        a = self.app.assets
        self._dim(surf)
        panel(surf, (S.SCREEN_W // 2 - 220, 130, 440, 480), S.UI_PANEL, radius=28, border=S.UI_ACCENT)
        blit_center(surf, a.text("PAUSED", 56, S.UI_ACCENT, shadow=True), (S.SCREEN_W // 2, 190))
        for b in self.buttons:
            b.draw(surf, a)

    def _draw_revive(self, surf):
        a = self.app.assets
        self._dim(surf, 120)
        cx = S.SCREEN_W // 2
        panel(surf, (cx - 260, 200, 520, 400), S.UI_PANEL, radius=28, border=S.UI_GOOD)
        blit_center(surf, a.text("CONTINUE?", 56, (255, 255, 255), shadow=True), (cx, 260))
        blit_center(surf, a.icon("key", 90, S.UI_ACCENT), (cx, 345))
        progress_bar(surf, (cx - 200, 395, 400, 14), self.revive_timer / 5.0, S.UI_GOOD)
        for b in self.buttons:
            b.draw(surf, a)

    def _draw_over(self, surf):
        a = self.app.assets
        res = self.session.result
        self._dim(surf, 170)
        cx = S.SCREEN_W // 2
        panel(surf, (cx - 380, 40, 760, 540), S.UI_PANEL, radius=30, border=S.UI_BAD)
        blit_center(surf, a.text("GAME OVER", 64, (255, 90, 90), shadow=True), (cx, 100))
        if res["new_best"]:
            t = pygame.time.get_ticks() / 1000
            img = a.text("NEW BEST SCORE!", 30, S.UI_ACCENT, shadow=True)
            img = pygame.transform.rotozoom(img, math.sin(t * 4) * 3, 1 + 0.05 * math.sin(t * 6))
            blit_center(surf, img, (cx, 150))
        rows = [
            ("Score", fmt_int(res["score"]), "star", S.UI_ACCENT),
            ("Distance", f"{fmt_int(res['distance'])} m", "distance", S.UI_ACCENT_2),
            ("Coins collected", fmt_int(res["coins"]), "coin", S.COIN_COLOR),
            ("XP earned", f"+{fmt_int(res['xp'])}", "upgrade", S.UI_GOOD),
            ("Best score", fmt_int(res["best"]), "trophy", (255, 160, 60)),
        ]
        if res["gems"]:
            rows.insert(3, ("Gems", f"+{res['gems']}", "gem", S.GEM_COLOR))
        if res.get("season_points"):
            season = self.app.season.current()
            col = season["color"] if season else S.UI_ACCENT_2
            rows.insert(4, ("Season points", f"+{fmt_int(res['season_points'])}", "star", col))
        if res["tokens"] and self.session.event:
            ev = self.session.event
            rows.insert(3, (ev["currency"]["name"], f"+{res['tokens']}", "token", ev["currency"]["color"]))
        y = 180
        for label, value, icon, col in rows:
            surf.blit(a.icon(icon, 34, col), (cx - 340, y))
            surf.blit(a.text(label, 26, S.UI_TEXT_DIM), (cx - 296, y + 4))
            v = a.text(value, 28, (255, 255, 255))
            surf.blit(v, (cx - 30 - v.get_width(), y + 3))
            y += 46
        # right column: missions & level
        x2 = cx + 20
        prog = self.app.progression
        surf.blit(a.text(f"LEVEL {prog.level}", 28, S.UI_ACCENT), (x2, 184))
        if res["level_up"]:
            t = pygame.time.get_ticks() / 1000
            lu = a.text("LEVEL UP!", 24, S.UI_GOOD)
            surf.blit(lu, (x2 + 170, 188 + math.sin(t * 6) * 3))
            rl = ", ".join(getattr(self, "level_lines", []))
            if rl:
                surf.blit(a.text(rl if len(rl) < 40 else rl[:38] + "..", 16, S.UI_TEXT_DIM), (x2, 520))
        progress_bar(surf, (x2, 222, 330, 16), prog.progress, S.UI_GOOD)
        surf.blit(a.text("Missions completed", 24, S.UI_TEXT_DIM), (x2, 256))
        my = 290
        if res["missions"]:
            for m in res["missions"][:4]:
                surf.blit(a.icon("mission", 24, S.UI_GOOD), (x2, my))
                surf.blit(a.text(m if len(m) < 30 else m[:28] + "...", 20, (255, 255, 255)), (x2 + 32, my + 2))
                my += 30
        else:
            surf.blit(a.text("None this run", 20, S.UI_TEXT_DIM), (x2, my))
            my += 30
        if res["achievements"]:
            my += 6
            surf.blit(a.text("Achievements", 24, S.UI_TEXT_DIM), (x2, my))
            my += 30
            for n in res["achievements"][:3]:
                surf.blit(a.icon("trophy", 24, S.UI_ACCENT), (x2, my))
                surf.blit(a.text(n, 20, (255, 255, 255)), (x2 + 32, my + 2))
                my += 30
        for b in self.buttons:
            b.draw(surf, a)

    def _draw_debug(self, surf):
        sess = self.session
        a = self.app.assets
        p = sess.player
        fps = self.app.clock.get_fps()
        zone = sess.world.schedule.zone_id_at(p.z)
        lines = [
            f"FPS: {fps:5.1f}",
            f"Speed: {sess.speed:5.1f} m/s",
            f"Chunk: {sess.world.chunk_index_at(p.z)}  (loaded {len(sess.world.chunks)})",
            f"Coins: {sess.coins}",
            f"Pos: x={p.x:5.2f} y={p.y:5.2f} z={p.z:8.1f} lane={p.lane}",
            f"Zone: {zone}",
            f"Difficulty: {sess.world.difficulty(p.z):.2f}",
            f"Draw items: {self.renderer.stats_drawn}  particles: {sess.particles.active}",
            f"Movers: {len(sess.world.movers)}  ground={p.ground_y:.2f}",
        ]
        w = 470
        layer = pygame.Surface((w, len(lines) * 24 + 16), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 170))
        surf.blit(layer, (10, S.SCREEN_H - layer.get_height() - 10))
        y = S.SCREEN_H - layer.get_height() - 2
        for ln in lines:
            surf.blit(a.text(ln, 18, (120, 255, 140), bold=False), (20, y))
            y += 24
