import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common


class SrcToRecord(unittest.TestCase):
    def test_same_fps(self):
        self.assertEqual(common.src_to_record(86400, 0, 240, 23.976, 23.976), 86640)

    def test_high_fps_runs_realtime(self):
        # 59,94-fps-Clip in 23,976-Timeline: 600 Quell-Frames = 240 Timeline-Frames
        self.assertEqual(common.src_to_record(86400, 0, 600, 23.976, 59.94), 86640)

    def test_trimmed_item(self):
        self.assertEqual(common.src_to_record(1000, 100, 160, 25, 50), 1030)


class SecondsToFrames(unittest.TestCase):
    def test_rounding(self):
        self.assertEqual(common.seconds_to_frames(1.0, 23.976), 24)
        self.assertEqual(common.seconds_to_frames(0.0, 23.976), 0)
        self.assertEqual(common.seconds_to_frames(10.0, 25), 250)


class ClaudeDir(unittest.TestCase):
    def test_creates_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = common.claude_dir(Path(tmp), "felix")
            self.assertEqual(root, Path(tmp) / "00 - FELIX" / "CLAUDE")
            for sub in ("SELECTS", "EDIT", "SOUND", "LOGS"):
                self.assertTrue((root / sub).is_dir())


class ProxyFor(unittest.TestCase):
    def test_finds_mov_in_proxy_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "A.MP4"
            clip.write_bytes(b"x")
            self.assertIsNone(common.proxy_for(clip))
            (Path(tmp) / "Proxy").mkdir()
            (Path(tmp) / "Proxy" / "A.mov").write_bytes(b"x")
            self.assertEqual(common.proxy_for(clip), Path(tmp) / "Proxy" / "A.mov")


if __name__ == "__main__":
    unittest.main()
