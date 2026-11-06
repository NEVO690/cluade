"""End-to-end UI flow tests driven by simulated mouse/keyboard input."""
import sys, os, json, tempfile, shutil
save_dir = tempfile.mkdtemp(prefix='ilb_flow_')
os.environ['ILBRAWL_SAVE_DIR'] = save_dir
sys.path.insert(0, os.path.dirname(__file__))
from harness import Harness
import pygame
from ilbrawl.ui.widgets import Button, ScrollPanel, Group

def all_buttons(scene):
    out = []
    def walk(ws, ox=0, oy=0):
        for w in ws:
            if isinstance(w, ScrollPanel):
                walk(w.children, w.rect.x - (w.offset if w.horizontal else 0), w.rect.y - (0 if w.horizontal else w.offset))
            elif isinstance(w, Group):
                w._sync(); walk([c[0] for c in w.children], ox, oy)
            elif isinstance(w, Button):
                out.append((w, w.rect.move(ox, oy)))
            elif hasattr(w, 'btn'):
                w._sync(); out.append((w.btn, w.btn.rect.move(ox, oy)))
    walk(scene.widgets)
    if scene.modal:
        out += [(b, b.rect) for b in scene.modal.buttons]
    return out

def label(b):
    l = b.label() if callable(b.label) else b.label
    return l or ''

def click_label(h, text, nth=0):
    hits = [(b, r) for b, r in all_buttons(h.scene) if text in label(b)]
    assert hits, 'no button %r in %s: %s' % (text, type(h.scene).__name__, [label(b) for b, _ in all_buttons(h.scene)])
    b, r = hits[nth]
    h.click(*r.center)
    h.frames(3)

failures = []
def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond: failures.append(msg)

h = Harness()          # default language must be Hebrew on first launch
g = h.g
check(g.i18n.lang == 'he' and g.i18n.rtl, 'Hebrew is the default language (RTL)')
tr = g.i18n.t

# --- every enabled button has an action -------------------------------------------------
from ilbrawl.menus.character_select import CharacterSelectScene
from ilbrawl.menus.modes_menu import ModesScene
from ilbrawl.menus.shop_menu import ShopScene
from ilbrawl.menus.missions_menu import MissionsScene
from ilbrawl.menus.trophy_road import TrophyRoadScene
from ilbrawl.menus.profile_menu import ProfileScene
from ilbrawl.menus.settings_menu import SettingsScene
from ilbrawl.maps.map_editor import MapEditorScene
dead = []
for mk in [lambda: g.scene, lambda: CharacterSelectScene(g), lambda: ModesScene(g), lambda: ShopScene(g),
           lambda: MissionsScene(g), lambda: TrophyRoadScene(g), lambda: ProfileScene(g), lambda: SettingsScene(g),
           lambda: MapEditorScene(g)]:
    sc = mk()
    for t in range(6):
        if hasattr(sc, 'set_tab') and hasattr(sc, 'tab'):
            try:
                sc.set_tab(t)
            except (IndexError, KeyError):
                break
        for b, r in all_buttons(sc):
            if b.enabled and b.on_click is None:
                dead.append((type(sc).__name__, label(b)))
        if not hasattr(sc, 'set_tab'):
            break
check(not dead, 'no enabled button without an action %s' % dead)

# --- main menu -> characters -> select pip ------------------------------------------------
click_label(h, tr('menu.characters'))
check(type(h.scene).__name__ == 'CharacterSelectScene', 'characters screen opens')
h.scene.select('pip'); h.frames(2)
click_label(h, tr('chars.select'))
check(g.profile.data['selected_char'] == 'pip', 'selecting a character works')
g.profile.data['coins'] = 1000
h.scene.build()
click_label(h, tr('chars.upgrade'))
click_label(h, tr('common.confirm'))
check(g.profile.char_level('pip') == 2 and g.profile.data['coins'] == 980, 'upgrade costs coins and raises level')
h.key(pygame.K_ESCAPE)
check(type(h.scene).__name__ == 'MainMenuScene', 'ESC goes back')

# --- shop purchase -------------------------------------------------------------------------
g.profile.data['coins'] = 2000
click_label(h, tr('menu.shop'))
h.scene.set_tab(2); h.frames(2)    # characters tab
click_label(h, '900')
click_label(h, tr('shop.buy'))
check(g.profile.is_unlocked('cinder') and g.profile.data['coins'] == 1100, 'buying a character in the shop')
h.scene.set_tab(0); h.frames(2)
click_label(h, tr('shop.free'))
click_label(h, tr('shop.buy'))
check(g.profile.data['coins'] == 1130, 'free daily gift grants coins')
g.profile.data['gems'] = 0
h.scene.set_tab(5); h.frames(2)
click_label(h, '10')
check(h.scene.modal is None and g.profile.data['coins'] == 1130, 'cannot buy without enough gems')
h.key(pygame.K_ESCAPE)

# --- daily reward ------------------------------------------------------------------------------
c0 = g.profile.data['coins']
click_label(h, tr('menu.daily_reward'))
click_label(h, tr('daily.claim'))
check(g.profile.data['coins'] == c0 + 50 and not g.profile.daily_reward_available(), 'daily reward claimed once')

# --- missions claim --------------------------------------------------------------------------
m0 = g.profile.data['missions']['list'][0]
m0['progress'] = m0['target']
click_label(h, tr('menu.missions'))
c0 = g.profile.data['coins']
click_label(h, tr('missions.claim'))
check(g.profile.data['missions']['list'][0]['claimed'] and g.profile.data['coins'] == c0 + m0['coins'], 'mission reward claimed')
h.key(pygame.K_ESCAPE)

# --- trophy road claim (unlock zippa) -------------------------------------------------------
g.profile.data['trophies']['nova'] = 60
g.profile.data['highest_trophies'] = 60
click_label(h, tr('menu.trophy_road'))
for _ in range(3):
    click_label(h, tr('missions.claim'))
check(g.profile.is_unlocked('zippa'), 'trophy road unlocks a character')
h.key(pygame.K_ESCAPE)

# --- language switch is instant and persisted -------------------------------------------------
click_label(h, tr('menu.settings'))
click_label(h, 'English')
check(g.i18n.lang == 'en' and not g.i18n.rtl, 'switch to English')
check(any(label(b) == 'Settings' or 'Reset' in label(b) for b, _ in all_buttons(h.scene)), 'settings screen re-labelled instantly')
h.key(pygame.K_ESCAPE)
check(any(label(b) == 'Shop' for b, _ in all_buttons(h.scene)), 'main menu re-labelled instantly (no restart)')
click_label(h, 'Settings')
click_label(h, 'العربية')
check(g.i18n.lang == 'ar' and g.i18n.rtl, 'switch to Arabic (RTL)')
click_label(h, 'Русский')
check(g.i18n.lang == 'ru', 'switch to Russian')
# control remap
h.scene.set_tab(1); h.frames(2)
click_label(h, 'E')
h.key(pygame.K_f)
check(g.settings['controls']['super'] == 'f', 'remap super key to F')
click_label(h, 'W')   # up
h.key(pygame.K_f)     # f already used -> swap
check(g.settings['controls']['up'] == 'f' and g.settings['controls']['super'] == 'w', 'duplicate binding is swapped')
click_label(h, g.i18n.t('settings.reset_controls'))
check(g.settings['controls']['super'] == 'e', 'reset controls')
h.scene.set_tab(0); h.frames(2)
click_label(h, 'עברית')
h.key(pygame.K_ESCAPE)

# --- map editor: paint, validate, save, reload ------------------------------------------------
from ilbrawl.maps.map_editor import MapEditorScene, validate
g.push(MapEditorScene(g)); h.frames(2)
ed = h.scene
gr, cell = ed.grid_rect
ed.set_brush('1'); h.frames(1)
h.click(gr.x + cell * 1 + 5, gr.y + cell * 9 + 5)
ed.set_brush('#'); h.frames(1)
pygame.mouse._pos = (gr.x + cell * 5 + 5, gr.y + cell * 3 + 5)
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pygame.mouse._pos, button=1)); h.frames(1)
for k in range(6):
    p = (gr.x + cell * 5 + 5, gr.y + cell * (3 + k) + 5)
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=p, rel=(0, 0), buttons=(1, 0, 0))); h.frames(1)
pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=p, button=1)); h.frames(1)
check(ed.tiles[9][1] == '1' and ed.tiles[9][29] == '2', 'editor mirror paints team spawns symmetrically')
check(sum(r.count('#') for r in ed.tiles) == 12, 'editor drag painting (6 walls + 6 mirrored)')
ed.name_input.value = 'Test Arena'
click_label(h, tr('editor.save'))
mid = ed.map_id
check(mid in g.data.maps and g.data.maps[mid]['custom'], 'custom map saved and loaded into the game')
data = json.load(open(g.data.maps[mid]['file'], encoding='utf-8'))
check(data['name'] == 'Test Arena' and len(data['tiles']) == 19, 'custom map file is valid JSON')
check(validate(['....'], ['gem_collection']) != [], 'editor validation rejects incomplete maps')
click_label(h, tr('editor.test'))
check(type(h.scene).__name__ == 'BattleScene', 'test play launches a battle on the custom map')
sc = h.scene
for _ in range(240): sc.update(1/60)
# pause + quit
h.key(pygame.K_ESCAPE)
check(sc.paused, 'ESC pauses the battle')
click_label(h, tr('pause.quit'))
click_label(h, tr('pause.quit'), nth=-1)
check(type(h.scene).__name__ == 'ResultsScene' and h.scene.result['outcome'] == 'loss', 'leaving a match counts as a loss')
click_label(h, tr('results.lobby'))
check(type(h.scene).__name__ == 'MainMenuScene', 'results -> lobby')
os.remove(g.data.maps[mid]['file'])

# --- full match from the PLAY button -----------------------------------------------------------
matches0 = g.profile.data['stats']['matches']
g.profile.data['selected_mode'] = 'team_survival'
click_label(h, tr('menu.play'))
check(type(h.scene).__name__ == 'BattleScene', 'PLAY starts a battle')
sc = h.scene
n = 0
while type(h.scene).__name__ == 'BattleScene' and n < 60 * 600:
    sc.update(1/30); n += 1
check(type(h.scene).__name__ == 'ResultsScene', 'match ends and shows results (%.0fs game time)' % sc.world.time)
check(g.profile.data['stats']['matches'] == matches0 + 1 and len(g.profile.data['history']) >= 1, 'stats & history updated')

# --- persistence: reload a fresh game from disk --------------------------------------------------
g.profile.save(); g.settings.save()
snap = json.load(open(os.path.join(save_dir, 'profile.json'), encoding='utf-8'))
h2 = Harness()
g2 = h2.g
check(g2.i18n.lang == 'he', 'language persisted')
check(g2.profile.data['coins'] == snap['coins'] and g2.profile.is_unlocked('cinder') and g2.profile.char_level('pip') == 2,
      'profile persisted (coins, unlocks, levels)')
# corrupt save recovery
with open(os.path.join(save_dir, 'profile.json'), 'w') as f:
    f.write('{broken')
h3 = Harness()
check(h3.g.profile.data['coins'] >= 0 and 'nova' in h3.g.profile.data['unlocked'], 'corrupted save recovers from backup')
print()
print('FAILURES:', len(failures))
shutil.rmtree(save_dir, ignore_errors=True)
sys.exit(1 if failures else 0)
