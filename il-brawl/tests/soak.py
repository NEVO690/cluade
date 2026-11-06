"""Soak test: many complete matches through the real scenes with every character, mode and map."""
import sys, os, random, time, tracemalloc
sys.path.insert(0, os.path.dirname(__file__))
from harness import Harness
h = Harness(); g = h.g
from ilbrawl.gameplay.battle_scene import BattleScene
from ilbrawl.ui import text
from ilbrawl.gameplay import renderer
random.seed(5)
tracemalloc.start()
t0 = time.time(); n = 0
for cid in g.data.char_order:
    for diff in ('easy', 'normal', 'hard', 'expert'):
        g.settings.data['ai_difficulty'] = diff
        g.settings.data['graphics'] = random.choice(['low', 'medium', 'high'])
        mode = random.choice(g.data.mode_order)
        m = random.choice(g.data.maps_for_mode(mode))['id']
        g.profile.data['unlocked'].append(cid)
        sc = BattleScene(g, mode, m, cid); g.push(sc)
        k = 0
        while g.scene is sc and k < 60 * 400:
            p = sc.world.player
            if p and p.alive:
                sc.attack_queued = random.random() < 0.2
                sc.super_queued = p.super_ready and random.random() < 0.05
                import pygame
                pygame.key._down = {random.choice([pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d])} if k % 30 == 0 else pygame.key._down
            sc.update(1/30); k += 1
            if k % 200 == 0:
                g.render()
        assert type(g.scene).__name__ == 'ResultsScene', (cid, mode, m)
        g.scene.update(0.5); g.render()
        g.pop_to_root(); n += 1
cur, peak = tracemalloc.get_traced_memory()
print('matches', n, 'in %.0fs' % (time.time() - t0), 'mem now %.1fMB peak %.1fMB' % (cur / 1e6, peak / 1e6),
      'text cache', len(text._cache), 'history', len(g.profile.data['history']), 'trophies', g.profile.total_trophies(),
      'level', g.profile.data['level'])
