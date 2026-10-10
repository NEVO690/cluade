"""In-lobby vertical video player (Panda3D MovieTexture, FFmpeg-backed)."""
from __future__ import annotations

import logging

from direct.gui.DirectGui import DirectFrame
from panda3d.core import AudioSound, CardMaker, MovieTexture, NodePath, TransparencyAttrib

from game.assets import fn

log = logging.getLogger(__name__)


class VideoPlayer:
    """Plays one video inside a 9:16 frame, letterboxing anything that isn't vertical."""

    def __init__(self, app, parent: NodePath, *, center=(0, 0), height=1.5):
        self.app = app
        self.height = height
        self.width = height * 9 / 16
        self.root = parent.attachNewNode("video-player")
        self.root.setPos(center[0], 0, center[1])
        DirectFrame(parent=self.root, frameSize=(-self.width / 2, self.width / 2, -height / 2, height / 2), frameColor=(0, 0, 0, 1))
        self.card = None
        self.tex = None
        self.sound = None
        self.paused = False
        self.error = None
        self.path = None
        self.progress = DirectFrame(parent=self.root, frameSize=(0, self.width, -0.003, 0.003), frameColor=(1, 1, 1, 0.8),
                                    pos=(-self.width / 2, 0, -height / 2 + 0.004))

    def load(self, path) -> bool:
        self.stop()
        self.path = path
        self.error = None
        tex = MovieTexture("video")
        try:
            ok = tex.read(fn(path))
        except Exception as exc:  # FFmpeg can raise on broken files
            log.warning("Video %s failed to open: %s", path, exc)
            ok = False
        if not ok or tex.getVideoWidth() <= 0:
            self.error = "This video can't be played. The file may be missing or corrupt."
            return False
        self.tex = tex
        vw, vh = tex.getVideoWidth(), tex.getVideoHeight()
        # fit inside the 9:16 frame
        frame_aspect = self.width / self.height
        aspect = vw / vh
        if aspect > frame_aspect:
            w, h = self.width, self.width / aspect
        else:
            w, h = self.height * aspect, self.height
        cm = CardMaker("video-card")
        cm.setFrame(-w / 2, w / 2, -h / 2, h / 2)
        cm.setUvRange(tex)  # textures are padded to a power of two on some GPUs
        self.card = self.root.attachNewNode(cm.generate())
        self.card.setTexture(tex)
        self.card.setTransparency(TransparencyAttrib.M_none)
        self.progress.reparentTo(self.root)  # keep the progress line above the video
        try:
            if self.app.sfxManagerList and self.app.sfxManagerList[0].isValid():
                self.sound = self.app.loader.loadSfx(fn(path))
                if self.sound is not None and self.sound.length() > 0:
                    tex.synchronizeTo(self.sound)
                    self.sound.setLoop(True)
                    self.sound.setVolume(self.app.settings.master_volume * self.app.settings.sfx_volume)
                    self.sound.play()
                else:
                    self.sound = None
        except Exception:  # silent videos are fine
            self.sound = None
        if self.sound is None:
            tex.setLoop(True)
            tex.play()
        self.paused = False
        return True

    @property
    def duration(self) -> float:
        return self.tex.getVideoLength() if self.tex else 0.0

    def toggle_pause(self) -> None:
        if self.tex is None:
            return
        self.paused = not self.paused
        target = self.sound if self.sound is not None else self.tex
        if self.paused:
            t = target.getTime()
            target.stop()
            target.setTime(t)
        else:
            if self.sound is not None:
                self.sound.setTime(self.sound.getTime())
                self.sound.play()
            else:
                self.tex.restart()

    def time(self) -> float:
        if self.sound is not None:
            return self.sound.getTime()
        return self.tex.getTime() if self.tex else 0.0

    def update(self) -> None:
        if self.tex is not None and self.duration > 0:
            self.progress.setSx(max(0.001, min(1.0, (self.time() % self.duration) / self.duration)))

    def stop(self) -> None:
        if self.sound is not None:
            self.sound.stop()
            self.sound = None
        if self.tex is not None:
            self.tex.stop()
            self.tex = None
        if self.card is not None:
            self.card.removeNode()
            self.card = None

    def destroy(self) -> None:
        self.stop()
        self.root.removeNode()


def pick_video_file() -> str | None:
    """Native file dialog in a helper process (keeps Tk out of the game's event loop)."""
    import subprocess
    import sys
    code = ("import tkinter as tk\nfrom tkinter import filedialog\nr=tk.Tk();r.withdraw();r.attributes('-topmost',True)\n"
            "p=filedialog.askopenfilename(title='Choose a video for Xgun',filetypes=[('Videos','*.mp4 *.m4v *.mov *.webm *.mkv *.avi *.ogv'),"
            "('All files','*.*')])\nprint(p or '')")
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
    except Exception as exc:
        log.info("File dialog unavailable: %s", exc)
        return None
    path = out.stdout.strip()
    return path or None
