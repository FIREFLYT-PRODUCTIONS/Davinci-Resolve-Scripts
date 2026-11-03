import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import place_selects as ps

# V1: Clip A (59,94 fps, 2010 Quell-Frames = 804 Timeline-Frames) ab 86400, Clip B (23,976) danach
V1 = [
    {"file": "a.mp4", "start": 86400, "end": 87204, "src_start": 0, "fps": 59.94},
    {"file": "b.mp4", "start": 87204, "end": 87444, "src_start": 0, "fps": 23.976},
]


def sel(file, start, end):
    return {"file": file, "start": start, "end": end}


class PlanPlacements(unittest.TestCase):
    def test_positions_with_fps_ratio(self):
        plan, skipped = ps.plan_placements([sel("A.MP4", 600, 840), sel("b.mp4", 24, 72)], V1, 23.976, [])
        self.assertEqual([(p["record"], p["start"], p["end"]) for p in plan],
                         [(86640, 600, 840), (87228, 24, 72)])
        self.assertEqual(skipped, [])

    def test_clamped_to_clip(self):
        plan, _ = ps.plan_placements([sel("b.mp4", 200, 400)], V1, 23.976, [])
        self.assertEqual((plan[0]["start"], plan[0]["end"]), (200, 240))

    def test_unknown_file_skipped(self):
        plan, skipped = ps.plan_placements([sel("c.mp4", 0, 48)], V1, 23.976, [])
        self.assertEqual(plan, [])
        self.assertEqual(skipped[0]["why"], "nicht in dieser Timeline")

    def test_take_with_existing_selects_skipped(self):
        plan, skipped = ps.plan_placements([sel("a.mp4", 0, 120), sel("b.mp4", 0, 48)], V1, 23.976,
                                           [(86500, 86600)])
        self.assertEqual([p["file"] for p in plan], ["b.mp4"])
        self.assertEqual(skipped[0]["why"], "Take hat schon Selects")


if __name__ == "__main__":
    unittest.main()
