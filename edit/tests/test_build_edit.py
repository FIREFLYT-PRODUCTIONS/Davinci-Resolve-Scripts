import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_edit as be

TAKES = [{"key": "T001", "file": "a.mp4", "fps": 23.976, "clean": [[0.0, 10.0]]},
         {"key": "T002", "file": "b.mp4", "fps": 59.94, "clean": [[2.0, 8.0]]}]
MUSIC = {"bars": [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]}
FPS = 24.0


def edit(**over):
    e = {"version": "v01", "format": {"width": 2160, "height": 3840, "fps": "24"},
         "music": {"file": "m.wav", "segments": [[0.0, 4.0], [8.0, 10.0]]},
         "shots": [{"key": "T001", "from": 1.0, "record": 0.0, "dur": 3.0, "track": "V1"},
                   {"key": "T002", "from": 2.0, "record": 3.0, "dur": 3.0, "track": "V1"},
                   {"key": "T001", "from": 5.0, "record": 3.0, "dur": 1.0, "track": "ALT 1"}],
         "markers": [{"at": 5.0, "name": "LOGO", "note": "x"}]}
    e.update(over)
    return e


class Validate(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(be.validate_edit(edit(), TAKES, MUSIC), [])

    def test_gap_on_v1(self):
        shots = edit()["shots"]
        shots[1]["record"] = 3.5
        problems = be.validate_edit(edit(shots=shots), TAKES, MUSIC)
        self.assertTrue(any("Luecke" in p for p in problems))

    def test_length_must_match_music(self):
        shots = edit()["shots"]
        shots[1]["dur"] = 2.0
        problems = be.validate_edit(edit(shots=shots), TAKES, MUSIC)
        self.assertTrue(any("Musik" in p for p in problems))

    def test_music_cut_off_bar(self):
        problems = be.validate_edit(edit(music={"file": "m.wav", "segments": [[0.0, 4.3], [8.0, 9.7]]}),
                                    TAKES, MUSIC)
        self.assertTrue(any("Takt" in p for p in problems))

    def test_shot_outside_clean(self):
        shots = edit()["shots"]
        shots[1]["from"] = 6.0  # 6..9 s, sauber nur bis 8
        problems = be.validate_edit(edit(shots=shots), TAKES, MUSIC)
        self.assertTrue(any("T002" in p for p in problems))

    def test_alt_needs_v1_partner(self):
        shots = edit()["shots"]
        shots[2]["record"] = 7.0
        problems = be.validate_edit(edit(shots=shots), TAKES, MUSIC)
        self.assertTrue(any("ALT" in p for p in problems))


class Frames(unittest.TestCase):
    def test_shot_frames_contiguous(self):
        plan = be.shot_frames(edit()["shots"], TAKES, FPS)
        v1 = [p for p in plan if p["track"] == "V1"]
        self.assertEqual([(p["rec"], p["len"]) for p in v1], [(0, 72), (72, 72)])
        self.assertEqual((v1[1]["src_in"], v1[1]["src_out"]), (120, 300))  # 59,94 fps: 2,5 Quellbilder pro Frame

    def test_no_extra_frame_from_fps_noise(self):
        # ffprobe meldet 23,976024, die Timeline 23,976: 23 Frames dürfen nicht 24 Quellbilder werden
        takes = [{"key": "T", "file": "c.mp4", "fps": 24000 / 1001, "clean": [[0, 10]]}]
        shots = [{"key": "T", "from": 0.6, "record": 0.0, "dur": 0.964, "track": "V1"}]
        p = be.shot_frames(shots, takes, 23.976)[0]
        self.assertEqual(p["len"], 23)
        self.assertEqual(p["src_out"] - p["src_in"], 23)

    def test_fill_zoom(self):
        self.assertAlmostEqual(be.fill_zoom(3840, 2160, 2160, 3840), 3840 / 1215, places=3)
        self.assertEqual(be.fill_zoom(2160, 3840, 2160, 3840), 1.0)


if __name__ == "__main__":
    unittest.main()
