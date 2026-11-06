"""Test harness: drives the real game with scripted input (headless) and can save screenshots.

Uses real pygame with SDL's dummy video/audio drivers. In the development sandbox, where pygame
is unavailable, it falls back to a PIL-based stand-in located in ../devtools (not shipped).
"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('ILBRAWL_SAVE_DIR', tempfile.mkdtemp(prefix='ilb_'))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
try:
    if os.environ.get('ILBRAWL_TEST_SHIM'):
        raise ImportError
    import pygame
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'devtools'))
    import pygame
from ilbrawl.engine.game import Game

class Harness:
    def __init__(self, lang=None):
        self.g = Game()
        if lang:
            self.g.set_language(lang)
        from ilbrawl.menus.main_menu import MainMenuScene
        self.g.push(MainMenuScene(self.g))
    def frames(self, n=1, dt=1/60):
        for _ in range(n):
            self.g.step(dt)
    def click(self, x, y, button=1):
        pygame.mouse._pos = (x, y)
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(x, y), rel=(0, 0), buttons=(0, 0, 0)))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=button))
        self.frames(1)
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x, y), button=button))
        self.frames(2)
    def move(self, x, y):
        pygame.mouse._pos = (x, y)
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(x, y), rel=(0, 0), buttons=(0, 0, 0)))
        self.frames(1)
    def key(self, k, text=None):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=text or ''))
        self.frames(1)
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=k, mod=0))
        self.frames(1)
    def shot(self, name):
        out = os.path.join(tempfile.gettempdir(), 'shots')
        os.makedirs(out, exist_ok=True)
        pygame.image.save(self.g.canvas, os.path.join(out, '%s.png' % name))
    @property
    def scene(self):
        return self.g.scene
