import json
import os
import tempfile
import unittest

import helpers  # noqa: F401  (sets up sys.path)

from bonk.save.save_manager import SaveManager, default_data, validate


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bonk_save_")
        self.sm = SaveManager(self.dir)

    def test_defaults_when_no_file(self):
        data = self.sm.load()
        self.assertEqual(data["wallet"]["coins"], 0)
        self.assertEqual(data["cosmetics"]["equipped_skin"], "classic")
        self.assertEqual(self.sm.warnings, [])

    def test_round_trip(self):
        data = self.sm.load()
        data["wallet"]["coins"] = 1234
        data["settings"]["player_name"] = "Tester"
        self.assertTrue(self.sm.save())
        again = SaveManager(self.dir).load()
        self.assertEqual(again["wallet"]["coins"], 1234)
        self.assertEqual(again["settings"]["player_name"], "Tester")

    def test_corrupt_file_does_not_crash(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.sm.path, "w") as fh:
            fh.write("{this is not json")
        data = self.sm.load()
        self.assertEqual(data["wallet"]["coins"], 0)
        self.assertTrue(any("damaged" in w for w in self.sm.warnings))
        self.assertTrue(any(f.startswith("profile.json.corrupt-") for f in os.listdir(self.dir)))

    def test_corrupt_file_falls_back_to_backup(self):
        data = self.sm.load()
        data["wallet"]["coins"] = 50
        self.sm.save()
        data["wallet"]["coins"] = 70
        self.sm.save()  # the 50-coin version is now the .bak
        with open(self.sm.path, "w") as fh:
            fh.write("garbage")
        restored = SaveManager(self.dir).load()
        self.assertEqual(restored["wallet"]["coins"], 50)

    def test_validation_clamps_bad_values(self):
        raw = default_data()
        raw["wallet"]["coins"] = -999
        raw["progress"]["level"] = 999
        raw["cosmetics"]["equipped_skin"] = "cosmic"  # not owned
        raw["settings"]["mouse_sensitivity"] = "fast"
        raw["settings"]["bot_count"] = 500
        raw["titles"]["equipped"] = "bonk_legend"  # not unlocked
        raw["stats"]["wins"] = "lots"
        clean = validate(raw)
        self.assertEqual(clean["wallet"]["coins"], 0)
        self.assertEqual(clean["progress"]["level"], 50)
        self.assertEqual(clean["cosmetics"]["equipped_skin"], "classic")
        self.assertEqual(clean["settings"]["mouse_sensitivity"], 1.0)
        self.assertEqual(clean["settings"]["bot_count"], 15)
        self.assertIsNone(clean["titles"]["equipped"])
        self.assertEqual(clean["stats"]["wins"], 0)

    def test_wrong_structure_is_replaced(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.sm.path, "w") as fh:
            json.dump({"data": ["not", "a", "dict"]}, fh)
        data = self.sm.load()
        self.assertEqual(data["wallet"]["coins"], 0)

    def test_atomic_write_leaves_no_temp_file(self):
        self.sm.load()
        self.sm.save()
        self.assertFalse(os.path.exists(self.sm.path + ".tmp"))
        with open(self.sm.path) as fh:
            wrapper = json.load(fh)
        self.assertIn("sha256", wrapper)

    def test_no_secrets_in_save(self):
        text = json.dumps(default_data()).lower()
        for word in ("password", "token", "secret"):
            self.assertNotIn(word, text)

    def test_save_failure_reported(self):
        self.sm.load()
        self.sm.save()  # profile.json is now a file, so it cannot be used as a directory
        bad = SaveManager(os.path.join(self.sm.path, "cannot_be_a_dir"))
        bad.data = default_data()
        self.assertFalse(bad.save())
        self.assertFalse(bad.last_save_ok)


if __name__ == "__main__":
    unittest.main()
