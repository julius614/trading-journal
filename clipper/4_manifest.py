"""Step 4: build a posting schedule (upload_manifest.csv) from the rendered clips.

Rules
- Every clip is scheduled ONCE, on exactly ONE account. Never duplicated across accounts.
- Each account posts at most its `daily_cap` clips per day (warm-up: 1).
- Only clips 28-62 s long are scheduled (config: schedule.clip_seconds).
- A clip rendered into output/<ACCOUNT_ID>/ (e.g. output/TT_01/) is pinned to that account.
  Clips in any other folder (pool, old tags) are shared out to whichever account has room.
- Scheduled clips are remembered in archive/scheduled.json, so re-running never repeats one.

Accounts come from config.json -> accounts, overridden by accounts_roster.csv
(local only, gitignored): account_id,platform,handle,daily_cap,active

Usage:
  python 4_manifest.py [--date 2026-11-22] [--days 3] [--seed 42] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
from pathlib import Path

from common import ROOT, get_path, load_config, probe_duration, setup_logging


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def post_times(n: int, start_min: int, end_min: int, gap_min: float, rng: random.Random) -> list[int]:
    """n random minutes in [start, end] with at least gap_min between each pair."""
    if n <= 0:
        return []
    slack = (end_min - start_min) - (n - 1) * gap_min
    if slack < 0:
        raise ValueError(f"{n} posts with {gap_min / 60:.1f}h gaps do not fit in the posting window")
    offsets = sorted(rng.uniform(0, slack) for _ in range(n))
    return [int(start_min + o + i * gap_min) for i, o in enumerate(offsets)]


def load_accounts(cfg: dict, log) -> dict[str, dict]:
    accounts = {}
    for aid, a in cfg.get("accounts", {}).items():
        accounts[aid] = {"platform": a.get("platform", ""), "handle": a.get("handle", ""),
                         "daily_cap": int(a.get("daily_cap", 1)), "active": bool(a.get("active", True))}
    roster = ROOT / cfg["schedule"].get("roster_file", "./accounts_roster.csv")
    if roster.exists():
        with open(roster, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                aid = (r.get("account_id") or "").strip()
                if not aid:
                    continue
                a = accounts.setdefault(aid, {"platform": "", "handle": "", "daily_cap": 1, "active": True})
                a["platform"] = (r.get("platform") or a["platform"]).strip()
                a["handle"] = (r.get("handle") or a["handle"]).strip()
                if (r.get("daily_cap") or "").strip():
                    a["daily_cap"] = int(r["daily_cap"])
                if (r.get("active") or "").strip():
                    a["active"] = r["active"].strip().lower() in ("yes", "y", "true", "1")
    else:
        log.info("No %s found: handles will be blank (copy accounts_roster.example.csv).", roster.name)
    return {k: v for k, v in accounts.items() if v["active"] and v["daily_cap"] > 0}


def load_cutlist(cfg: dict) -> dict:
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
    lo_s, hi_s = sch.get("clip_seconds", [28, 62])

    accounts = load_accounts(cfg, log)
    if not accounts:
        log.error("No active accounts with daily_cap > 0.")
        return

    used_path = get_path(cfg, "archive") / "scheduled.json"
    used = set(json.loads(used_path.read_text(encoding="utf-8"))) if used_path.exists() else set()
    used_ids = {Path(u).stem for u in used}
    cut = load_cutlist(cfg)
    order = {cid: i for i, cid in enumerate(cut)}

    # Collect unscheduled clips, check length, split into pinned (per account) and shared pool.
    pinned: dict[str, list] = {a: [] for a in accounts}
    pool: list = []
    seen_ids: set[str] = set()
    for f in sorted(get_path(cfg, "output").rglob("*.mp4"), key=lambda p: (order.get(p.stem, 10**6), p.name)):
        rel = str(f.relative_to(ROOT))
        cid = f.stem
        if rel in used or cid in used_ids or cid in seen_ids:
            continue  # already scheduled, or a duplicate copy of the same clip
        seen_ids.add(cid)
        dur = probe_duration(f)
        if not lo_s <= dur <= hi_s:
            log.warning("skip %s: %.1fs is outside %d-%ds", cid, dur, lo_s, hi_s)
            continue
        clip = {"file": rel, "clip_id": cid, "dur": dur}
        if f.parent.name in accounts:
            pinned[f.parent.name].append(clip)
        else:
            pool.append(clip)

    gap = sch["min_gap_hours"] * 60
    w0, w1 = hm(sch["window_start"]), hm(sch["window_end"])
    rows, acc_ids = [], list(accounts)
    for d in range(args.days):
        day = first + dt.timedelta(days=d)
        rng.shuffle(acc_ids)  # nobody always gets first pick of the pool
        for aid in acc_ids:
            a = accounts[aid]
            picks = []
            while len(picks) < a["daily_cap"] and (pinned[aid] or pool):
                picks.append(pinned[aid].pop(0) if pinned[aid] else pool.pop(0))
            for minute, clip in zip(post_times(len(picks), w0, w1, gap, rng), picks):
                info = cut.get(clip["clip_id"], {})
                rows.append({
                    "date": day.isoformat(),
                    "post_time": f"{minute // 60:02d}:{minute % 60:02d}",
                    "timezone": sch.get("timezone_label", "local"),
                    "account_id": aid,
                    "platform": a["platform"],
                    "handle": a["handle"],
                    "clip_id": clip["clip_id"],
                    "seconds": f"{clip['dur']:.1f}",
                    "hook_text": info.get("hook_text", ""),
                    "streamer": info.get("streamer", ""),
                    "file": clip["file"],
                    "posted": "",
                })
    rows.sort(key=lambda r: (r["date"], r["post_time"], r["account_id"]))

    # Safety net: a clip must never appear twice.
    ids = [r["clip_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate clip in manifest"

    if not rows:
        log.info("No unscheduled clips (28-62 s) found in output/.")
        return
    for r in rows:
        log.info("%s %s  %-5s %-16s %-14s %5ss  %s", r["date"], r["post_time"], r["account_id"],
                 r["platform"], r["clip_id"], r["seconds"], r["hook_text"])
    left = len(pool) + sum(len(v) for v in pinned.values())
    log.info("%d posts scheduled, %d clips left for later days", len(rows), left)
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
    log.info("Wrote %s", out)


if __name__ == "__main__":
    main()
