"""Step 3: render every PENDING row of cutlist.csv into a 1080x1920 split-screen clip.

Layout: webcam (top 672 px), gameplay (bottom 1248 px), word-highlight captions on the
seam, a 3.2 s hook banner, loudness normalised to -14 LUFS, container metadata removed.

Usage:
  python 3_batch_render.py [--cutlist cutlist.csv] [--workers 2] [--only clip_007] [--redo]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from captions import build_ass
from common import (ROOT, check_crop_fits, find_analysis_words, get_path, load_config, parse_crop,
                    parse_time, probe_video_size, require_ffmpeg, resolve_vod, run, setup_logging)

COLUMNS = ["clip_id", "streamer", "vod_file", "start_time", "end_time", "hook_text", "account_tag", "status"]


def read_cutlist(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in COLUMNS:
            r.setdefault(k, "")
            r[k] = (r[k] or "").strip()
    return rows


def write_cutlist(path: Path, rows: list[dict]) -> None:
    fields = COLUMNS + [k for k in rows[0].keys() if k not in COLUMNS] if rows else COLUMNS
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    for _ in range(5):  # Excel may hold a lock on Windows; retry briefly
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(1)
    raise PermissionError(f"Could not update {path}. Close it in Excel and run again.")


def fit_filter(crop: str, w: int, h: int, mode: str) -> str:
    cw, ch, cx, cy = parse_crop(crop)
    base = f"crop={cw}:{ch}:{cx}:{cy}"
    if mode == "pad":
        return (f"{base},scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    return (f"{base},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h},setsar=1")


def clip_words(words_path: Path, start: float, end: float) -> list[dict]:
    if not words_path.exists():
        return []
    words = json.loads(words_path.read_text(encoding="utf-8"))["words"]
    return [{"s": w["s"] - start, "e": w["e"] - start, "w": w["w"]}
            for w in words if w["s"] >= start - 0.05 and w["s"] < end]


def find_font_file(cfg: dict) -> str | None:
    fonts_dir = ROOT / cfg["render_settings"]["captions"].get("fonts_dir", "./fonts")
    if fonts_dir.is_dir():
        for f in sorted(fonts_dir.iterdir()):
            if f.suffix.lower() in (".ttf", ".otf"):
                return str(f)
    for cand in ("C:/Windows/Fonts/ariblk.ttf", "/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(cand).exists():
            return cand
    return None


def render_one(job: dict) -> tuple[str, str, str]:
    """Runs in a worker process. Returns (clip_id, status, message)."""
    cfg, row = job["cfg"], job["row"]
    rs = cfg["render_settings"]
    clip_id = row["clip_id"]
    try:
        vod = resolve_vod(cfg, row["vod_file"])
        start, end = parse_time(row["start_time"]), parse_time(row["end_time"])
        length = end - start
        # Per-clip overrides: a stream's layout changes (game vs. just chatting), so a row
        # may set its own webcam_crop / gameplay_crop, or layout=fit (whole frame, no split).
        prof = dict(cfg["streamers"][row["streamer"]])
        for key in ("webcam_crop", "gameplay_crop"):
            if (row.get(key) or "").strip():
                prof[key] = row[key].strip()
        layout = (row.get("layout") or "split").strip().lower()
        src_w, src_h = probe_video_size(vod)
        if layout == "split":
            for key in ("webcam_crop", "gameplay_crop"):
                check_crop_fits(prof[key], src_w, src_h)
        elif layout == "fit":
            # video sits in the middle, so move captions below it and the hook above it
            rs = json.loads(json.dumps(rs))
            rs["captions"]["y"] = rs.get("fit_caption_y", 1420)
            rs["hook"]["y"] = rs.get("fit_hook_y", 470)
        else:
            raise ValueError(f"layout must be 'split' or 'fit', got {layout!r}")

        W, H = (int(v) for v in rs["resolution"].split("x"))
        top_h, bot_h = rs["webcam_height"], rs["gameplay_height"]
        highlight = random.Random(clip_id).choice(rs["captions"]["highlight_pool"])

        out_dir = get_path(cfg, "output") / (row["account_tag"] or "unassigned")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{clip_id}.mp4"

        with tempfile.TemporaryDirectory(prefix=f"clip_{clip_id}_") as tmp:
            tmp = Path(tmp)
            words = clip_words(find_analysis_words(cfg, vod), start, end)
            font_file = find_font_file(cfg)
            build_ass(words, length, row["hook_text"], rs, highlight, tmp / "subs.ass", font_file)

            fonts_dir = ROOT / rs["captions"].get("fonts_dir", "./fonts")
            ass_opt = "ass=subs.ass"
            if fonts_dir.is_dir():
                # copy fonts next to the .ass so the path needs no escaping (Windows drive colons)
                shutil.copytree(fonts_dir, tmp / "fonts", dirs_exist_ok=True)
                ass_opt += ":fontsdir=fonts"

            ln = rs["loudnorm"]
            if layout == "fit":
                video = (f"[0:v]fps={rs['fps']},split=2[a][b];"
                         f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                         f"boxblur=20:2,eq=brightness=-0.12,setsar=1[bg];"
                         f"[b]scale={W}:-2:flags=lanczos,setsar=1[fg];"
                         f"[bg][fg]overlay=0:(H-h)/2,{ass_opt},format=yuv420p[v];")
            else:
                video = (f"[0:v]fps={rs['fps']},split=2[a][b];"
                         f"[a]{fit_filter(prof['webcam_crop'], W, top_h, rs.get('webcam_fit', 'cover'))}[top];"
                         f"[b]{fit_filter(prof['gameplay_crop'], W, bot_h, 'cover')}[bot];"
                         f"[top][bot]vstack=inputs=2,{ass_opt},format=yuv420p[v];")
            fc = (video +
                  f"[0:a]loudnorm=I={ln['I']}:TP={ln['TP']}:LRA={ln['LRA']},"
                  f"aresample=48000[aout]")

            enc = rs.get("video_encoder", "libx264")
            venc = ["-c:v", enc]
            if enc == "libx264":
                venc += ["-preset", rs.get("x264_preset", "veryfast"), "-crf", str(rs.get("crf", 20)),
                         "-profile:v", "high", "-threads", str(job["threads"])]
            else:  # e.g. h264_nvenc / h264_qsv / h264_amf
                venc += ["-b:v", "8M", "-maxrate", "12M", "-bufsize", "16M"]

            tmp_out = tmp / "out.mp4"
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
                   "-i", str(vod), "-filter_complex", fc, "-map", "[v]", "-map", "[aout]",
                   *venc, "-c:a", "aac", "-b:a", rs.get("audio_bitrate", "192k"),
                   "-map_metadata", "-1", "-map_chapters", "-1",
                   "-metadata", "title=", "-metadata", "encoder=", "-fflags", "+bitexact",
                   "-movflags", "+faststart", str(tmp_out)]
            run(cmd, cwd=tmp)
            shutil.move(str(tmp_out), out_path)
        return clip_id, "DONE", f"{out_path.relative_to(ROOT)} ({length:.1f}s, highlight={highlight}, {len(words)} words)"
    except Exception as e:  # noqa: BLE001
        return clip_id, "FAILED", str(e)[-1500:]


def validate(row: dict, cfg: dict) -> str | None:
    rs = cfg["render_settings"]
    if not row["clip_id"]:
        return "missing clip_id"
    if row["streamer"] not in cfg["streamers"]:
        return f"unknown streamer '{row['streamer']}'"
    try:
        length = parse_time(row["end_time"]) - parse_time(row["start_time"])
    except ValueError as e:
        return str(e)
    if not rs["min_clip_seconds"] <= length <= rs["max_clip_seconds"]:
        return f"length {length:.1f}s is outside {rs['min_clip_seconds']}-{rs['max_clip_seconds']}s"
    if (row.get("layout") or "split").strip().lower() not in ("split", "fit"):
        return f"layout must be split or fit, got {row.get('layout')!r}"
    if row["account_tag"] and cfg.get("accounts") and row["account_tag"] not in cfg["accounts"]:
        return f"account_tag '{row['account_tag']}' is not in config.json accounts"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cutlist", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--only", nargs="*", help="render just these clip_ids")
    ap.add_argument("--redo", action="store_true", help="also re-render rows marked DONE")
    args = ap.parse_args()

    cfg = load_config()
    log = setup_logging(cfg, "render")
    require_ffmpeg()
    cut_path = Path(args.cutlist) if args.cutlist else get_path(cfg, "cutlist")
    rows = read_cutlist(cut_path)

    seen, todo = set(), []
    for r in rows:
        if r["clip_id"] in seen:
            r["status"] = "ERROR: duplicate clip_id"
            continue
        seen.add(r["clip_id"])
        if args.only and r["clip_id"] not in args.only:
            continue
        if r["status"].upper() == "DONE" and not args.redo:
            continue
        err = validate(r, cfg)
        if err:
            r["status"] = f"ERROR: {err}"
            log.warning("%s skipped: %s", r["clip_id"], err)
            continue
        todo.append(r)
    write_cutlist(cut_path, rows)

    if not todo:
        log.info("Nothing to render. (Rows marked DONE are skipped; use --redo to force.)")
        return
    workers = args.workers or cfg["render_settings"].get("render_workers", 2)
    threads = max(1, (os.cpu_count() or 4) // workers)
    log.info("Rendering %d clips with %d workers (%d threads each)", len(todo), workers, threads)

    by_id = {r["clip_id"]: r for r in rows}
    t0, done, failed = time.time(), 0, 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(render_one, {"cfg": cfg, "row": r, "threads": threads}) for r in todo]
        for fut in as_completed(futures):
            clip_id, status, msg = fut.result()
            by_id[clip_id]["status"] = status if status == "DONE" else f"FAILED: {msg.splitlines()[-1][:120]}"
            write_cutlist(cut_path, rows)  # only the main process writes the CSV
            if status == "DONE":
                done += 1
                log.info("DONE %s -> %s", clip_id, msg)
            else:
                failed += 1
                log.error("FAILED %s\n%s", clip_id, msg)
    log.info("Finished: %d done, %d failed in %.1f min", done, failed, (time.time() - t0) / 60)


if __name__ == "__main__":
    main()
