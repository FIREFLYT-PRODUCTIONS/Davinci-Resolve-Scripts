import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_selects as ms

TAKES = [{"key": "T001", "file": "a.mp4", "fps": 59.94, "clean": [[0.0, 5.0], [7.0, 20.0]]},
         {"key": "T002", "file": "b.mp4", "fps": 23.976, "clean": [[1.0, 4.0]]}]


def d(key, a, b):
    return {"key": key, "from": a, "to": b, "rating": 4, "why": "x", "content": "y"}


class BuildSelects(unittest.TestCase):
    def test_converts_to_source_frames(self):
        sel, notes = ms.build_selects([d("T002", 1.5, 3.5)], TAKES)
        self.assertEqual((sel[0]["start"], sel[0]["end"]), (36, 84))
        self.assertEqual(sel[0]["file"], "b.mp4")

    def test_split_around_rejected_part(self):
        sel, notes = ms.build_selects([d("T001", 2.0, 10.0)], TAKES)
        self.assertEqual([(s["start"], s["end"]) for s in sel], [(120, 300), (420, 599)])
        self.assertTrue(notes)

    def test_drop_parts_under_2s(self):
        sel, _ = ms.build_selects([d("T001", 4.0, 8.0)], TAKES)
        self.assertEqual(sel, [])

    def test_unknown_key(self):
        sel, notes = ms.build_selects([d("T999", 0, 3)], TAKES)
        self.assertEqual(sel, [])
        self.assertIn("T999", notes[0])


if __name__ == "__main__":
    unittest.main()
