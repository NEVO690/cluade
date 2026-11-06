"""Run a battle in each mode with scripted player input and screenshot it."""
import sys, os, random, time
sys.path.insert(0, os.path.dirname(__file__))
from harness import Harness
import pygame
lang = sys.argv[1] if len(sys.argv) > 1 else 'he'
modes = sys.argv[2].split(',') if len(sys.argv) > 2 else None
h = Harness(lang)
g = h.g
from ilbrawl.gameplay.battle_scene import BattleScene
random.seed(3)
for mode in g.data.mode_order:
    if modes and mode not in modes:
        continue
    maps = g.data.maps_for_mode(mode)
    m = maps[0]['id']
    g.profile.data['selected_char'] = random.choice(['nova', 'rocko', 'pip'])
    sc = BattleScene(g, mode, m, g.profile.data['selected_char'])
    g.push(sc)
    t0 = time.time()
    # countdown frame
    for _ in range(30): sc.update(1/60)
    g.fade = 0; g.render(); h.shot('%s_battle_%s_a' % (lang, mode))
    w = sc.world
    pygame.key._down = {pygame.K_d}
    for i in range(60 * 9):
        p = w.player
        if p and p.alive:
            # aim at the nearest enemy and hold attack
            en = [b for b in w.brawlers if b.alive and b.team != p.team]
            if en:
                e = min(en, key=lambda b: (b.x-p.x)**2 + (b.y-p.y)**2)
                sx, sy = sc.renderer.world_to_screen(e.x, e.y)
                pygame.mouse._pos = (int(sx), int(sy))
                sc.lmb = (i % 40) < 6
                if p.super_ready: sc.super_queued = True
            pygame.key._down = {[pygame.K_d, pygame.K_s, pygame.K_w, pygame.K_a][(i // 90) % 4]}
        sc.update(1/60)
        g.mouse_pos = pygame.mouse._pos
        if w.state == 'over': break
    g.fade = 0; g.render(); h.shot('%s_battle_%s_b' % (lang, mode))
    # run to the end quickly without player input
    pygame.key._down = set(); sc.lmb = False
    n = 0
    while g.scene is sc and n < 60 * 400:
        sc.update(1/30); n += 1
    print(w.result, w.mode.final_score_text(), [(b.team,b.gems) for b in w.brawlers]); print(mode, m, 'state', w.state, 'time %.0f' % w.time, 'scene', type(g.scene).__name__, 'real %.1fs' % (time.time() - t0))
    for _ in range(40): g.scene.update(1/60)
    g.fade = 0; g.render(); h.shot('%s_results_%s' % (lang, mode))
    g.pop_to_root()
print('profile trophies', g.profile.total_trophies(), 'coins', g.profile.data['coins'], 'matches', g.profile.data['stats']['matches'])
