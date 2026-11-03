import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transcribe


def seg(text, no_speech=0.1, words=3):
    return {"start": 0, "end": 1, "text": text, "no_speech": no_speech,
            "words": [[0, 0.1, "w"]] * words}


class SpeechSegments(unittest.TestCase):
    def test_too_few_words_is_no_speech(self):
        self.assertEqual(transcribe.speech_segments([seg("Musik", words=2)]), [])

    def test_drops_no_speech_segments(self):
        kept = transcribe.speech_segments([seg("Hallo zusammen", words=4), seg("Ähm", 0.9, 3),
                                           seg("schön dass ihr da seid", words=5)])
        self.assertEqual([s["text"] for s in kept], ["Hallo zusammen", "schön dass ihr da seid"])


if __name__ == "__main__":
    unittest.main()
