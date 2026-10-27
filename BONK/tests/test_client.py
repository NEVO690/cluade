"""Client-side checks that need Panda3D but no window: assets, animations, course views."""

import json
import os
import unittest

import helpers  # noqa: F401

try:
    from panda3d.core import loadPrcFileData
    loadPrcFileData("bonk-tests", "window-type none\naudio-library-name null")
    from direct.showbase.ShowBase import ShowBase
    import gltf  # noqa: F401
    HAVE_PANDA = True
except ImportError:  # pragma: no cover
    HAVE_PANDA = False

from bonk.paths import MODELS_DIR

_BASE = None


def base():
    global _BASE
    if _BASE is None:
        _BASE = ShowBase()
    return _BASE


@unittest.skipUnless(HAVE_PANDA, "Panda3D not installed")
class AssetTests(unittest.TestCase):
    def test_character_glb_has_skeleton_and_all_animations(self):
        from direct.actor.Actor import Actor
        from panda3d.core import Filename
        b = base()
        actor = Actor(b.loader.loadModel(Filename.fromOsSpecific(os.path.join(MODELS_DIR, "bonk_character.glb"))))
        self.assertEqual(set(actor.getAnimNames()),
                         {"Idle", "Walk", "Run", "Jump", "Fall", "Land", "Victory", "Elimination"})
        joints = {j.getName() for j in actor.getJoints()}
        for bone in ("root", "hips", "spine", "head", "antenna", "arm.L", "arm.R", "leg.L", "leg.R"):
            self.assertIn(bone, joints)
        for name in ("Bonk_Body", "Bonk_Accent", "Bonk_Visor", "Bonk_Eyes"):
            self.assertFalse(actor.find("**/" + name).isEmpty(), name)
        for anim in actor.getAnimNames():
            self.assertGreater(actor.getNumFrames(anim), 5, anim)
        actor.cleanup()

    def test_metadata_matches_model(self):
        with open(os.path.join(MODELS_DIR, "bonk_character.json")) as fh:
            meta = json.load(fh)
        self.assertEqual(len(meta["animations"]), 8)
        self.assertTrue(meta["animations"]["Run"]["loop"])
        self.assertFalse(meta["animations"]["Jump"]["loop"])
        self.assertGreater(meta["animations"]["Run"]["native_speed"], meta["animations"]["Walk"]["native_speed"])

    def test_all_accessories_and_props_load(self):
        from panda3d.core import Filename
        b = base()
        for f in sorted(os.listdir(MODELS_DIR)):
            if f.endswith(".glb"):
                np_ = b.loader.loadModel(Filename.fromOsSpecific(os.path.join(MODELS_DIR, f)))
                self.assertFalse(np_.isEmpty(), f)
                self.assertGreater(len(np_.findAllMatches("**/+GeomNode")), 0, f)


@unittest.skipUnless(HAVE_PANDA, "Panda3D not installed")
class AnimationControllerTests(unittest.TestCase):
    def setUp(self):
        from bonk.client.render.character_view import CharacterModel
        from bonk.cosmetics.skin_definitions import SkinCatalog
        self.model = CharacterModel(base().loader, SkinCatalog().get("royal"), base().render)

    def tearDown(self):
        self.model.destroy()

    def test_states_map_to_clips_with_blending(self):
        anim = self.model.anim
        for state, clip in (("IDLE", "Idle"), ("WALK", "Walk"), ("RUN", "Run"), ("JUMP", "Jump"),
                            ("FALL", "Fall"), ("LAND", "Land"), ("VICTORY", "Victory"),
                            ("ELIMINATED", "Elimination"), ("TUMBLE", "Fall")):
            for _ in range(20):
                anim.update(state, 0.0, 1 / 60.0)
            self.assertEqual(anim.current, clip, state)
            self.assertAlmostEqual(anim.weights[clip], 1.0, places=3)

    def test_play_rate_follows_ground_speed(self):
        anim = self.model.anim
        actor = self.model.actor
        anim.update("RUN", 6.8, 1 / 60.0)
        self.assertAlmostEqual(actor.getPlayRate("Run"), 6.8 / 3.4, places=3)
        anim.update("WALK", 1.8, 1 / 60.0)
        self.assertAlmostEqual(actor.getPlayRate("Walk"), 1.0, places=3)

    def test_animations_follow_real_physics(self):
        """Jumping in the simulation drives Jump -> Fall -> Land -> Idle in the animation layer."""
        from bonk.sim import constants as C
        from bonk.sim.character import Character, InputCommand
        from bonk.sim.obstacles import Solid
        from bonk.sim.physics import step_character
        from bonk.sim.world import CourseWorld
        w = CourseWorld("t", "t")
        w.add_solid(Solid("floor", (0, 0, -0.5), (40, 40, 1)))
        ch = Character("c", "c")
        ch.place_at(0, 0, 0)
        anim = self.model.anim
        t = 0.0
        for i in range(150):
            jump = i == 10
            w.update(t, C.DT)
            step_character(ch, InputCommand(0, 0.0, jump), w, t, C.DT)
            anim.update(ch.state, ch.speed, C.DT)
            t += C.DT
        seq = [c for i, c in enumerate(anim.history) if i == 0 or anim.history[i - 1] != c]
        # A full jump lands faster than HARD_LANDING_SPEED, so LAND plays before IDLE.
        self.assertEqual(seq[:5], ["Idle", "Jump", "Fall", "Land", "Idle"])

    def test_skin_change_swaps_accessory(self):
        from bonk.cosmetics.skin_definitions import SkinCatalog
        cat = SkinCatalog()
        self.assertIsNotNone(self.model.accessory)  # royal = crown
        self.model.apply_skin(cat.get("classic"))
        self.assertIsNone(self.model.accessory)
        self.model.apply_skin(cat.get("propeller"))
        self.assertEqual(len(self.model.spin_nodes), 1)


@unittest.skipUnless(HAVE_PANDA, "Panda3D not installed")
class CourseViewTests(unittest.TestCase):
    def test_every_course_builds_and_animates(self):
        from bonk.client.render.course_view import CourseView
        from bonk.maps.map_manager import MapManager
        mm = MapManager()
        for m in mm.ordered():
            world = m.build_world()
            view = CourseView(base(), m, world)
            dyn = len([s for s in world.solids if s.moving]) + len(world.tiles)
            self.assertEqual(len(view.movers) + len(view.tiles), dyn, m.id)
            self.assertEqual(len(view.hammers) + len(view.sweepers), len(world.hazards), m.id)
            for h, pivot, _ in view.hammers:
                view.update(h.period / 4.0, 0.016)  # max swing
                world_head = base().render.getRelativePoint(pivot, (0, 0, -h.length))
                hx, hy, hz = h.head_center(h.period / 4.0)
                self.assertAlmostEqual(world_head.x, hx, delta=0.05, msg="hammer drawn where it hits")
                self.assertAlmostEqual(world_head.y, hy, delta=0.05)
                self.assertAlmostEqual(world_head.z, hz, delta=0.05)
            for tile in world.tiles[:3]:
                tile.triggered_at = 0.0
            view.update(world.tiles[0].warn_time + 0.5 if world.tiles else 1.0, 0.016)
            if world.tiles:
                self.assertTrue(view.tiles[0][1].isHidden())
            view.destroy()


if __name__ == "__main__":
    unittest.main()
