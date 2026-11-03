import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyse_takes as at

RNG = np.random.default_rng(7)
SCENE = cv2.GaussianBlur((RNG.random((400, 600)) * 255).astype(np.uint8), (0, 0), 1.2)


def crop(dx=0, dy=0, blur=0):
    """180x320-Ausschnitt einer festen Szene, verschoben um dx/dy Pixel."""
    frame = SCENE[40 + dy:220 + dy, 100 + dx:420 + dx].copy()
    if blur:
        frame = cv2.GaussianBlur(frame, (0, 0), blur)
    return frame


def measure(frames):
    return at.measure_frames(frames)


class Classify(unittest.TestCase):
    def flags(self, frames, global_sharp=None):
        samples = measure(frames)
        if global_sharp is None:
            global_sharp = float(np.median([s["sharp"] for s in samples]))
        return at.classify(samples, global_sharp)

    def test_steady_sharp_is_clean(self):
        frames = [crop(dx=i) for i in range(20)]  # langsamer Schwenk, 1 px pro Bild
        self.assertTrue(all(f is None for f in self.flags(frames)))

    def test_blur_section_detected(self):
        frames = [crop(blur=4 if 8 <= i < 14 else 0) for i in range(20)]
        flags = self.flags(frames)
        self.assertTrue(all(flags[i] == "unscharf" for i in range(8, 14)))
        self.assertTrue(all(flags[i] is None for i in range(0, 6)))

    def test_shake_detected(self):
        jitter = [0, 9, -8, 10, -9, 8, -10, 9, -8, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        frames = [crop(dx=40 + j, dy=20 - j) for j in jitter]
        flags = self.flags(frames)
        self.assertIn("wackelig", flags[1:9])
        self.assertTrue(all(f is None for f in flags[13:]))

    def test_whip_pan_detected(self):
        offsets = [0, 0, 0, 0, 0, 60, 120, 180, 180, 180, 180, 180]
        frames = [crop(dx=o) for o in offsets]
        flags = self.flags(frames)
        self.assertIn("Reissschwenk", flags[5:8])
        self.assertIsNone(flags[1])

    def test_dark_frames_detected(self):
        frames = [crop() if not 6 <= i < 10 else (crop() * 0.1).astype(np.uint8) for i in range(16)]
        flags = self.flags(frames)
        self.assertTrue(all(flags[i] in ("Belichtung", "unscharf") for i in range(6, 10)))


class Segments(unittest.TestCase):
    def test_min_length_and_merge(self):
        # 4 Proben pro Sekunde: 3 s sauber, 0,5 s schlecht, 1 s sauber, 0,5 s schlecht, 2,5 s sauber
        flags = [None] * 12 + ["wackelig"] * 2 + [None] * 4 + ["unscharf"] * 2 + [None] * 10
        clean, rejected = at.segments(flags, step=0.25, min_len=2.0)
        self.assertEqual(clean, [[0.0, 3.0], [5.0, 7.5]])
        self.assertEqual([r["why"] for r in rejected], ["wackelig", "zu kurz", "unscharf"])


class TileTimes(unittest.TestCase):
    def test_spread_over_segments(self):
        times = at.tile_times([[0.0, 3.0], [10.0, 20.0]], max_tiles=6)
        self.assertEqual(len(times), 6)
        self.assertTrue(all(0.0 <= t <= 3.0 or 10.0 <= t <= 20.0 for t in times))
        self.assertGreaterEqual(sum(1 for t in times if t <= 3.0), 1)
        self.assertEqual(times, sorted(times))


if __name__ == "__main__":
    unittest.main()
