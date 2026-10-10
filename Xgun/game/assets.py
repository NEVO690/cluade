"""Model / texture / font loading with caching, plus the asset manifest."""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from panda3d.core import Filename, NodePath, SamplerState, Texture, TextureStage

from config import paths

log = logging.getLogger(__name__)


def fn(path) -> Filename:
    return Filename.from_os_specific(str(path))


class AssetLibrary:
    def __init__(self, base):
        self.base = base
        self.loader = base.loader
        self.manifest = json.loads(paths.MODEL_MANIFEST.read_text(encoding="utf-8")) if paths.MODEL_MANIFEST.exists() else {}
        self._models: dict[str, NodePath] = {}
        self._textures: dict[str, Texture] = {}
        self.missing: set[str] = set()

    def info(self, asset_id: str) -> dict:
        return self.manifest.get(asset_id, {})

    def model_file(self, asset_id: str):
        info = self.info(asset_id)
        rel = info.get("model")
        return paths.MODELS / rel if rel else None

    def model(self, asset_id: str) -> NodePath:
        """A fresh copy of a static model (instances share geometry)."""
        if asset_id not in self._models:
            path = self.model_file(asset_id)
            node = None
            if path and path.exists():
                try:
                    node = self.loader.loadModel(fn(path))
                except Exception as exc:  # broken asset must never crash the game
                    log.error("Failed to load %s: %s", path, exc)
            if node is None:
                self.missing.add(asset_id)
                node = self._placeholder()
            self.prepare(node)
            self._models[asset_id] = node
        return self._models[asset_id].copyTo(NodePath(asset_id))

    def prepare(self, node: NodePath) -> NodePath:
        """Adapt loaded models to the renderer: basic (no-shader) pipes can't use sRGB textures."""
        if getattr(self.base, "shaders_ok", True):
            return node
        for tex in node.findAllTextures():
            fmt = tex.getFormat()
            if fmt in (Texture.F_srgb, Texture.F_srgb_alpha, Texture.F_sluminance, Texture.F_sluminance_alpha):
                tex.setFormat(Texture.F_rgba if fmt in (Texture.F_srgb_alpha, Texture.F_sluminance_alpha) else Texture.F_rgb)
        return node

    def _placeholder(self) -> NodePath:
        from panda3d.core import CardMaker
        cm = CardMaker("missing")
        cm.setFrame(-0.5, 0.5, 0, 1)
        np = NodePath(cm.generate())
        np.setColor(1, 0, 1, 1)
        np.setTwoSided(True)
        return np

    def texture(self, path, *, mipmap: bool = True) -> Texture | None:
        key = str(path)
        if key not in self._textures:
            try:
                tex = self.loader.loadTexture(fn(path))
            except Exception as exc:
                log.warning("Texture %s missing: %s", path, exc)
                tex = None
            if tex is not None:
                tex.setMinfilter(SamplerState.FT_linear_mipmap_linear if mipmap else SamplerState.FT_linear)
                tex.setMagfilter(SamplerState.FT_linear)
                tex.setAnisotropicDegree(4)
            self._textures[key] = tex
        return self._textures[key]

    def thumb(self, asset_id: str) -> Texture | None:
        path = paths.THUMBS / f"{asset_id}.png"
        return self.texture(path, mipmap=False) if path.exists() else None

    def sound_path(self, name: str):
        for folder, ext in ((paths.SFX, ".wav"), (paths.MUSIC, ".ogg"), (paths.MUSIC, ".wav")):
            p = folder / f"{name}{ext}"
            if p.exists():
                return p
        return None


def apply_wrap(node: NodePath, tex: Texture | None) -> None:
    """Recolour wrappable weapon surfaces (materials named *_wrap*). Cosmetic only."""
    from panda3d.core import Material, MaterialAttrib, TextureAttrib
    for gnp in node.findAllMatches("**/+GeomNode"):
        gnode = gnp.node()
        for i in range(gnode.getNumGeoms()):
            state = gnode.getGeomState(i)
            mattr = state.getAttrib(MaterialAttrib)
            if mattr is None or mattr.getMaterial() is None or "_wrap" not in mattr.getMaterial().getName():
                continue
            if tex is None:
                continue
            mat = Material(mattr.getMaterial())
            mat.setBaseColor((1, 1, 1, 1))
            state = state.setAttrib(MaterialAttrib.make(mat))
            state = state.setAttrib(TextureAttrib.make(tex))
            gnode.setGeomState(i, state)
