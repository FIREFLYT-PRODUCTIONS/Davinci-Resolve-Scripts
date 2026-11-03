import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import place_sound as ps


def item(track, at, dur, **kw):
    return {"track": track, "file": "x.wav", "at": at, "in": 0.0, "dur": dur, "source": "artlist", "why": "", **kw}


class Validate(unittest.TestCase):
    def test_valid(self):
        sound = {"level_db": -15, "items": [item("SFX", 1.0, 1.0), item("SFX", 2.0, 0.5), item("ATMO", 0, 30)]}
        self.assertEqual(ps.validate_sound(sound, 30.7), [])

    def test_overlap_on_same_track(self):
        sound = {"level_db": -15, "items": [item("SFX", 1.0, 1.5), item("SFX", 2.0, 0.5)]}
        self.assertTrue(any("ueberlappt" in p for p in ps.validate_sound(sound, 30.7)))

    def test_outside_timeline(self):
        sound = {"level_db": -15, "items": [item("SFX", 30.0, 2.0)]}
        self.assertTrue(any("Timeline" in p for p in ps.validate_sound(sound, 30.7)))

    def test_unknown_track(self):
        sound = {"level_db": -15, "items": [item("MUSIK", 1.0, 1.0)]}
        self.assertTrue(any("Spur" in p for p in ps.validate_sound(sound, 30.7)))

    def test_level_required_and_quiet(self):
        sound = {"level_db": 0, "items": []}
        self.assertTrue(any("Pegel" in p for p in ps.validate_sound(sound, 30.7)))


class Tracks(unittest.TestCase):
    def test_track_names_in_order(self):
        sound = {"items": [item("ATMO", 0, 5), item("SFX 2", 1, 1), item("SFX", 2, 1)]}
        self.assertEqual(ps.track_names(sound), ["SFX", "SFX 2", "ATMO"])


if __name__ == "__main__":
    unittest.main()
