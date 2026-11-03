"""
FIREFLYT Edit – Auswahl in selects.json umwandeln
=================================================
Claude schreibt seine Auswahl in Sekunden je Take-Key (SELECTS\\selects_draft.json).
Dieses Skript schneidet jeden Select auf die technisch sauberen Abschnitte aus
takes.json zu, teilt ihn bei Bedarf, verwirft Reste unter 2 s und rechnet in
Quell-Frames um. So landet nie ein unscharfer oder wackeliger Bereich in den Selects.

USAGE:
  python make_selects.py "<Projektordner>" [--editor FELIX]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

MIN_LEN = 2.0


def build_selects(draft, takes):
    """Rein, testbar. draft: [{key, from, to, rating, why, content}] in Sekunden."""
    by_key = {t["key"]: t for t in takes}
    selects, notes = [], []
    for item in draft:
        take = by_key.get(item["key"])
        if not take:
            notes.append(f"{item['key']}: unbekannter Take")
            continue
        parts = [(max(item["from"], a), min(item["to"], b)) for a, b in take["clean"]]
        parts = [(a, b) for a, b in parts if b - a >= MIN_LEN]
        covered = sum(b - a for a, b in parts)
        if covered < item["to"] - item["from"] - 0.01:
            notes.append(f"{item['key']} {item['from']}-{item['to']}s: auf saubere Abschnitte gekuerzt "
                         f"({covered:.1f}s bleiben)")
        for a, b in parts:
            selects.append({"key": item["key"], "file": take["file"],
                            "start": round(a * take["fps"]), "end": round(b * take["fps"]),
                            "seconds": [round(a, 2), round(b, 2)], "rating": item.get("rating"),
                            "why": item.get("why", ""), "content": item.get("content", "")})
    return selects, notes


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Selects aus Claudes Auswahl")
    parser.add_argument("folder")
    parser.add_argument("--editor", default="CONRAD")
    args = parser.parse_args()
    root = common.claude_dir(args.folder, args.editor)
    takes = common.load_json(root / "SELECTS" / "takes.json")["takes"]
    draft = common.load_json(root / "SELECTS" / "selects_draft.json")["selects"]
    selects, notes = build_selects(draft, takes)
    common.save_json(root / "SELECTS" / "selects.json", {"selects": selects})
    for note in notes:
        print(f"  ~ {note}")
    seconds = sum(s["seconds"][1] - s["seconds"][0] for s in selects)
    print(f"{len(selects)} Selects aus {len({s['key'] for s in selects})} Takes, {seconds / 60:.1f} Min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
