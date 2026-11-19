"""Print a compact, timestamped review of the top candidate windows, to paste to Claude.

Usage:
  python review.py --input vods\\speed_2026-11-19.mp4 [--top 12]
  python review.py --input vods\\speed_2026-11-19.mp4 --after 30:00 --before 60:00 --top 15
  python review.py --input vods\\speed_2026-11-19.mp4 --from 3:00 --to 5:30   (full transcript of a range)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import fmt_time, get_path, load_config, parse_time


def lines_for(words: list[dict], start: float, end: float, line_s: float = 6.0) -> list[str]:
    out, cur, cur_t = [], [], None
    for w in words:
        if w["s"] < start or w["s"] >= end:
            continue
        if cur_t is None or w["s"] - cur_t >= line_s:
            if cur:
                out.append(f"  {fmt_time(cur_t)[:8]}  {' '.join(cur)}")
            cur, cur_t = [], w["s"]
        cur.append(w["w"])
    if cur:
        out.append(f"  {fmt_time(cur_t)[:8]}  {' '.join(cur)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="the VOD file (or its name)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--from", dest="t_from", default=None)
    ap.add_argument("--to", dest="t_to", default=None)
    ap.add_argument("--after", default=None, help="only candidates starting at/after this time")
    ap.add_argument("--before", default=None, help="only candidates ending at/before this time")
    args = ap.parse_args()

    cfg = load_config()
    stem = Path(args.input).stem
    adir = get_path(cfg, "analysis")
    words = json.loads((adir / f"{stem}_words.json").read_text(encoding="utf-8"))["words"]

    if args.t_from:
        s, e = parse_time(args.t_from), parse_time(args.t_to or args.t_from)
        e = e if e > s else s + 90
        print(f"=== {stem}  {fmt_time(s)[:8]} - {fmt_time(e)[:8]}")
        print("\n".join(lines_for(words, s, e)))
        return

    data = json.loads((adir / f"{stem}_analyzed.json").read_text(encoding="utf-8"))
    cands = data["candidates"]
    if args.after:
        cands = [c for c in cands if c["start"] >= parse_time(args.after)]
    if args.before:
        cands = [c for c in cands if c["end"] <= parse_time(args.before)]
    rng = f"  window {args.after or 'start'}-{args.before or 'end'}" if (args.after or args.before) else ""
    print(f"=== {stem}  ({data['duration_hms'][:8]})  top {min(args.top, len(cands))} of {len(cands)}{rng}")
    for c in cands[: args.top]:
        print(f"\n#{c['rank']}  {c['start_hms'][:8]}-{c['end_hms'][:8]}  score {c['hype_score']}  "
              f"loudest {c['peak_hms'][:8]}")
        print("\n".join(lines_for(words, c["start"], c["end"])))


if __name__ == "__main__":
    main()
