"""Summarize and render a saved debug-log session (written by jetson/debug_log.py).

Owner: Daniel

    python3 jetson/debug_report.py logs/<session>                    # text summary
    python3 jetson/debug_report.py logs/<session> --render           # + every saved frame annotated
    python3 jetson/debug_report.py logs/<session> --render --marks   # + only frames around marks

Annotated frames go to <session>/annotated/<seq>.jpg (or --out), oriented like the game. The
summary explains iffy detections: how many hands each frame had, why hands were rejected, signs
that nearly cleared the score threshold and which finger or palm measure held them back, stereo
depth dropouts, and what each hand looked like in the seconds before every mark (key B).
"""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

from debug_log import CAPTURE_FPS, RING_SECONDS, annotate, fmt

MIN_SCORE = 0.65  # game/src/vision/tuning.js SIGN.MIN_SCORE
NEAR_MISS = 0.45  # best sign score at or above this, but below MIN_SCORE, is a near miss
MATCH_SEQS = 5  # a frame uses the newest record at most this many captures older
BEFORE_MARK_MS = 2000


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("session", type=Path)
    parser.add_argument("--render", action="store_true", help="write annotated frames")
    parser.add_argument(
        "--marks", action="store_true", help="with --render: only frames near marks"
    )
    parser.add_argument("--out", type=Path, help="annotated frame directory")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE)
    return parser.parse_args()


def load_lines(path):
    if not path.exists():
        return []
    out = []
    for line in path.open():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a line cut short by a crash
    return out


def median(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(values) if values else None


def hand_brief(hand):
    scores = hand.get("scores") or {}
    best = max(scores, key=scores.get) if scores else "-"
    return (
        f"P{hand['slot'] + 1} {hand.get('handedness', '?')[:1]} sign {hand.get('sign')}"
        f" frame {hand.get('frameSign')} best {best} {fmt(scores.get(best))}"
        f" facing {fmt(hand.get('facing'))} z {fmt(hand.get('depth'))}"
    )


def summarize(records, marks, min_score):
    hands = [h for r in records for h in r.get("hands", [])]
    rejected = [h for r in records for h in r.get("rejected", [])]
    span_s = (records[-1]["t"] - records[0]["t"]) / 1000 if len(records) > 1 else 0
    print(f"records {len(records)} over {span_s:.0f} s, marks {len(marks)}")
    stats = [r.get("stats") or {} for r in records]
    print(
        f"median rates: hands {fmt(median(s.get('hands') for s in stats), 1)} Hz,"
        f" inference {fmt(median(s.get('inferMs') for s in stats), 1)} ms,"
        f" render {fmt(median(s.get('render') for s in stats), 0)} fps,"
        f" tracker {fmt(median(s.get('tracker') for s in stats), 1)} fps"
    )
    print(
        "accepted hands per record:",
        dict(sorted(Counter(len(r["hands"]) for r in records).items())),
    )
    for slot in (0, 1):
        seated = sum(1 for r in records if (r.get("bodies") or [None, None])[slot])
        with_hand = sum(1 for r in records if any(h["slot"] == slot for h in r["hands"]))
        n = max(len(records), 1)
        print(f"P{slot + 1}: body seated {seated / n:.0%}, hand seen {with_hand / n:.0%}")
    print("rejected hands by reason:", dict(Counter(h.get("reason") for h in rejected)))
    print("smoothed signs:", dict(Counter(h.get("sign") for h in hands)))
    print("frame signs:   ", dict(Counter(h.get("frameSign") for h in hands)))
    dropouts = sum(1 for h in hands if h.get("depth") is None)
    print(f"stereo depth dropouts on accepted hands: {dropouts} of {len(hands)}")

    misses = Counter()
    features = {}
    for h in hands:
        scores = h.get("scores") or {}
        if h.get("frameSign") != "none" or not scores:
            continue
        best = max(scores, key=scores.get)
        if NEAR_MISS <= scores[best] < min_score:
            misses[best] += 1
            features.setdefault(best, []).append(h)
    print(f"near misses (best score {NEAR_MISS}-{min_score}, read as no sign):", dict(misses))
    for sign, group in features.items():
        fingers = ("index", "middle", "ring", "pinky")
        ext = {f: median((h.get("ext") or {}).get(f) for h in group) for f in fingers}
        print(
            f"  {sign}: median ext "
            + " ".join(f"{k} {fmt(v)}" for k, v in ext.items())
            + f", facing {fmt(median(h.get('facing') for h in group))}"
            + f", thumbRise {fmt(median(h.get('thumbRise') for h in group))}"
        )

    for mark in marks:
        before = [r for r in records if 0 <= mark["t"] - r["t"] <= BEFORE_MARK_MS]
        print(f"\nmark at seq {mark.get('seq')}: {len(before)} records in the 2 s before")
        for r in before[:: max(1, len(before) // 8)]:
            dt = (r["t"] - mark["t"]) / 1000
            seen = "; ".join(hand_brief(h) for h in r["hands"]) or "no hands"
            gone = ", ".join(h.get("reason", "?") for h in r.get("rejected", []))
            tail = f"  [rejected: {gone}]" if gone else ""
            print(f"  {dt:+.1f}s seq {r['seq']}: {seen}{tail}")


def render(session, records, marks, out, only_marks):
    by_seq = {r["seq"]: r for r in records}
    bodies = {}
    for line in (session / "zed.jsonl").open() if (session / "zed.jsonl").exists() else []:
        seq = json.loads(line).get("seq")
        bodies[seq] = line.rstrip("\n")
    window = RING_SECONDS * CAPTURE_FPS
    marked = [m["seq"] for m in marks if isinstance(m.get("seq"), int)]
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted((session / "frames").glob("*.jpg")):
        seq = int(path.stem)
        if only_marks and not any(0 <= m - seq <= window for m in marked):
            continue
        record = next((by_seq[s] for s in range(seq, seq - MATCH_SEQS, -1) if s in by_seq), None)
        (out / path.name).write_bytes(annotate(path.read_bytes(), bodies.get(seq), record))
        count += 1
    print(f"\nrendered {count} annotated frames to {out}")


def main():
    args = parse_args()
    messages = load_lines(args.session / "telemetry.jsonl")
    records = [m for m in messages if m.get("type") == "debug"]
    marks = [m for m in messages if m.get("type") == "mark"]
    if not records and not marks:
        raise SystemExit(f"no records in {args.session / 'telemetry.jsonl'}")
    summarize(records, marks, args.min_score)
    if args.render:
        render(args.session, records, marks, args.out or args.session / "annotated", args.marks)


if __name__ == "__main__":
    main()
