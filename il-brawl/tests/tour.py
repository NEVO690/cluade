"""Visit every screen and save screenshots. Usage: python tests/tour.py [lang]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from harness import Harness
import pygame
lang = sys.argv[1] if len(sys.argv) > 1 else 'he'
h = Harness(lang)
g = h.g
g.profile.data['coins'] = 2500; g.profile.data['gems'] = 300
h.frames(20); h.shot(lang + '_01_main')
from ilbrawl.menus.character_select import CharacterSelectScene
from ilbrawl.menus.modes_menu import ModesScene
from ilbrawl.menus.shop_menu import ShopScene
from ilbrawl.menus.missions_menu import MissionsScene
from ilbrawl.menus.trophy_road import TrophyRoadScene
from ilbrawl.menus.profile_menu import ProfileScene
from ilbrawl.menus.settings_menu import SettingsScene
from ilbrawl.maps.map_editor import MapEditorScene
from ilbrawl.menus.splash import SplashScene
screens = [
 ('02_chars', lambda: CharacterSelectScene(g)),
 ('03_modes', lambda: ModesScene(g)),
 ('04_shop', lambda: ShopScene(g)),
 ('05_shop_chars', lambda: ShopScene(g, tab=2)),
 ('06_missions', lambda: MissionsScene(g)),
 ('07_achievements', lambda: MissionsScene(g, tab=1)),
 ('08_daily', lambda: MissionsScene(g, tab=2)),
 ('09_road', lambda: TrophyRoadScene(g)),
 ('10_profile', lambda: ProfileScene(g)),
 ('11_stats', lambda: ProfileScene(g, tab=1)),
 ('12_settings', lambda: SettingsScene(g)),
 ('13_controls', lambda: SettingsScene(g, tab=1)),
 ('14_editor', lambda: MapEditorScene(g)),
 ('00_splash', lambda: SplashScene(g)),
]
only = sys.argv[2].split(',') if len(sys.argv) > 2 else None
for name, mk in screens:
    if only and not any(name.startswith(o) for o in only):
        continue
    g.push(mk()); h.frames(25); h.shot(lang + '_' + name); g.pop(); h.frames(1)
print('ok')
