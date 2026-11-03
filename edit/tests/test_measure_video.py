import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measure_video as mv


class MeasureVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "cuts.mp4"
        # Schnitte bei 1,0 / 2,5 / 5,0 s, Gesamtlänge 6 s
        parts = [("testsrc2=", 1.0), ("color=c=red:", 1.5), ("smptebars=", 2.5), ("color=c=blue:", 1.0)]
        inputs = []
        for source, dur in parts:
            inputs += ["-f", "lavfi", "-i", f"{source}s=320x180:r=25:d={dur}"]
        filt = "".join(f"[{i}:v]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1[v]"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", filt, "-map", "[v]",
                        str(cls.path)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_cuts(self):
        info = mv.measure(self.path)
        self.assertAlmostEqual(info["duration"], 6.0, delta=0.1)
        self.assertEqual(len(info["cuts"]), 3)
        for got, want in zip(info["cuts"], [1.0, 2.5, 5.0]):
            self.assertAlmostEqual(got, want, delta=0.05)
        self.assertEqual(info["hook_cuts"], 2)
        self.assertAlmostEqual(info["avg_shot"], 1.5, delta=0.05)


class Summary(unittest.TestCase):
    def test_shots_from_cuts(self):
        self.assertEqual(mv.shot_lengths([1.0, 2.5], 4.0), [1.0, 1.5, 1.5])


if __name__ == "__main__":
    unittest.main()
