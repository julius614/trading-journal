"""Step 4: build a posting schedule (upload_manifest.csv) from the rendered clips.

Each clip is scheduled once, on the account it was rendered for (its output/<account_tag>
folder). Each account gets 3-4 posts per day at random times at least 3.5 h apart.
Scheduled clips are remembered in archive/scheduled.json so they are not scheduled twice.

Usage:
  python 4_manifest.py [--date 2026-11-20] [--days 1] [--seed 42] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
from pathlib import Path

from common import ROOT, get_path, load_config, setup_logging


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def post_times(n: int, start_min: int, end_min: int, gap_min: float, rng: random.Random) -> list[int]:
    """n random minutes in [start, end] with at least gap_min between each pair."""
    slack = (end_min - start_min) - (n - 1) * gap_min
    if slack < 0:
        raise ValueError(f"{n} posts with {gap_min / 60:.1f}h gaps do not fit in the posting window")
    offsets = sorted(rng.uniform(0, slack) for _ in range(n))
    return [int(start_min + o + i * gap_min) for i, o in enumerate(offsets)]


def load_cutlist_hooks(cfg: dict) -> dict:
    path = get_path(cfg, "cutlist")
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["clip_id"]: r for r in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=None, help="first day (YYYY-MM-DD), default tomorrow")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print but do not save or mark clips as used")
    args = ap.parse_args()

    cfg = load_config()
    log = setup_logging(cfg, "manifest")
    sch = cfg["schedule"]
    rng = random.Random(args.seed)
    first = dt.date.fromisoformat(args.date) if args.date else dt.date.today() + dt.timedelta(days=1)

    used_path = get_path(cfg, "archive") / "scheduled.json"
    used = set(json.loads(used_path.read_text(encoding="utf-8"))) if used_path.exists() else set()
    hooks = load_cutlist_hooks(cfg)

    out_root = get_path(cfg, "output")
    pools: dict[str, list[Path]] = {}
    for acc_dir in sorted(p for p in out_root.iterdir() if p.is_dir()):
        clips = sorted(c for c in acc_dir.glob("*.mp4") if str(c.relative_to(ROOT)) not in used)
        rng.shuffle(clips)
        pools[acc_dir.name] = clips

    accounts = cfg.get("accounts", {})
    lo, hi = sch["posts_per_account_per_day"]
    gap = sch["min_gap_hours"] * 60
    w0, w1 = hm(sch["window_start"]), hm(sch["window_end"])

    rows = []
    for d in range(args.days):
        day = first + dt.timedelta(days=d)
        for acc, pool in pools.items():
            n = min(rng.randint(lo, hi), len(pool))
            if n == 0:
                continue
            for minute in post_times(n, w0, w1, gap, rng):
                clip = pool.pop()
                cid = clip.stem
                rows.append({
                    "date": day.isoformat(),
                    "post_time": f"{minute // 60:02d}:{minute % 60:02d}",
                    "timezone": sch.get("timezone_label", "local"),
                    "account_tag": acc,
                    "platforms": "|".join(accounts.get(acc, {}).get("platforms", [])),
                    "clip_id": cid,
                    "file": str(clip.relative_to(ROOT)),
                    "hook_text": hooks.get(cid, {}).get("hook_text", ""),
                    "streamer": hooks.get(cid, {}).get("streamer", ""),
                    "posted": "",
                })
    rows.sort(key=lambda r: (r["date"], r["post_time"], r["account_tag"]))

    if not rows:
        log.info("No unscheduled clips found in %s", out_root)
        return
    for r in rows:
        log.info("%s %s  %-18s %s  %s", r["date"], r["post_time"], r["account_tag"], r["clip_id"], r["hook_text"])
    for acc, pool in pools.items():
        if pool:
            log.info("%s: %d clips left for later days", acc, len(pool))
    if args.dry_run:
        log.info("Dry run: nothing saved.")
        return

    out = get_path(cfg, "manifest")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    used.update(r["file"] for r in rows)
    used_path.write_text(json.dumps(sorted(used), indent=1), encoding="utf-8")
    log.info("Wrote %s with %d posts", out, len(rows))


if __name__ == "__main__":
    main()
