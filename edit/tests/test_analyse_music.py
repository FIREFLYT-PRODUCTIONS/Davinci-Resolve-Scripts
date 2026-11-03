import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyse_music as am

SR = 22050


def click_track(bpm=120, beats=64, first_downbeat=1, quiet_until_bar=8):
    """Klick pro Beat, die Eins betont und tiefer, ab Takt quiet_until_bar lauter (Drop)."""
    period = 60.0 / bpm
    y = np.zeros(int(SR * (beats * period + 1)))
    t = np.arange(int(0.05 * SR)) / SR
    for b in range(beats):
        accent = (b - first_downbeat) % 4 == 0
        freq = 220 if accent else 1200
        amp = (1.0 if accent else 0.4) * (0.3 if b < quiet_until_bar * 4 + first_downbeat else 1.0)
        start = int(b * period * SR)
        y[start:start + t.size] += amp * np.sin(2 * np.pi * freq * t) * np.exp(-t * 60)
    return y


class AnalyseMusic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "click.wav"
        sf.write(path, click_track(), SR)
        cls.info = am.analyse(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_tempo(self):
        self.assertAlmostEqual(self.info["tempo"], 120, delta=2)

    def test_bar_length(self):
        bars = np.diff(self.info["bars"])
        self.assertAlmostEqual(float(np.median(bars)), 2.0, delta=0.05)

    def test_downbeat_phase(self):
        # Erste Eins liegt auf Beat 1, also bei 0,5 s
        first = self.info["bars"][0]
        self.assertAlmostEqual(first % 2.0, 0.5, delta=0.06)

    def test_drop_found(self):
        # Lauter ab Takt 8 + 1 Beat: 8 * 2,0 + 0,5 = 16,5 s
        self.assertAlmostEqual(self.info["drop"], 16.5, delta=0.6)

    def test_sections_on_bars(self):
        for s in self.info["sections"]:
            self.assertTrue(any(abs(s["start"] - b) < 0.02 for b in self.info["bars"]) or s["start"] == 0.0)


class SnapToBars(unittest.TestCase):
    def test_snap(self):
        self.assertEqual(am.snap(3.1, [0.0, 2.0, 4.0]), 4.0)
        self.assertEqual(am.snap(2.9, [0.0, 2.0, 4.0]), 2.0)


if __name__ == "__main__":
    unittest.main()
