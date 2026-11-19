"""Step 1: download a VOD at up to 1080p and save a preview frame for crop checking.

Usage:
  python 1_ingest.py --streamer kai --url <vod_url> [--max-hours 4]
  python 1_ingest.py --streamer kai --latest           (newest VOD from channel_url)
  python 1_ingest.py --streamer kai --preview-only vods/kai_2026-11-19.mp4
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from common import (ROOT, resolve_streamer, check_crop_fits, get_path, load_config, parse_crop, probe_duration,
                    probe_video_size, require_ffmpeg, run, setup_logging)

FORMAT = ("bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
          "bv*[height<=1080]+ba/"
          "b[height<=1080]/b")


def next_free_name(folder: Path, stem: str) -> Path:
    path = folder / f"{stem}.mp4"
    n = 2
    while path.exists():
        path = folder / f"{stem}_{n}.mp4"
        n += 1
    return path


def download(url: str, out_path: Path, max_hours: float | None, latest: bool, log) -> None:
    cmd = [sys.executable, "-m", "yt_dlp", url,
           "-f", FORMAT, "--merge-output-format", "mp4",
           "-o", str(out_path), "--no-part", "--concurrent-fragments", "8",
           "--retries", "10", "--fragment-retries", "10"]
    if latest:
        cmd += ["--playlist-items", "1"]
    else:
        cmd += ["--no-playlist"]
    if max_hours:
        secs = int(max_hours * 3600)
        cmd += ["--download-sections", f"*0-{secs}", "--force-keyframes-at-cuts"]
    log.info("Downloading: %s", url)
    proc = subprocess.run(cmd)
    if proc.returncode != 0 or not out_path.exists():
        raise SystemExit(f"yt-dlp failed (exit {proc.returncode}). See the messages above.")


def make_previews(vod: Path, streamer: str, profile: dict, log) -> None:
    duration = probe_duration(vod)
    t = 15 * 60 if duration > 16 * 60 else duration / 2
    plain = ROOT / f"preview_{streamer}.png"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(vod),
         "-frames:v", "1", str(plain)])
    log.info("Preview frame: %s (at %.0fs)", plain, t)

    # Second image with the configured crop boxes drawn on top, so you can check them.
    src_w, src_h = probe_video_size(vod)
    boxes = []
    for key, color in (("webcam_crop", "red"), ("gameplay_crop", "lime")):
        w, h, x, y = parse_crop(profile[key])
        try:
            check_crop_fits(profile[key], src_w, src_h)
        except ValueError as e:
            log.warning("%s: %s", key, e)
        boxes.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}@0.9:t=6")
    boxed = ROOT / f"preview_{streamer}_boxes.png"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(plain), "-vf", ",".join(boxes), str(boxed)])
    log.info("Crop check image: %s  (red = webcam_crop, green = gameplay_crop)", boxed)
    log.info("Source is %dx%d. Crops in config.json are for this size.", src_w, src_h)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--streamer", required=True, help="key from config.json -> streamers")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="VOD URL (Twitch, YouTube, Kick ...)")
    src.add_argument("--latest", action="store_true", help="newest VOD from the streamer's channel_url")
    src.add_argument("--preview-only", metavar="VOD", help="skip download, just make preview images")
    ap.add_argument("--max-hours", type=float, default=None, help="only download the first N hours")
    args = ap.parse_args()

    cfg = load_config()
    log = setup_logging(cfg, "ingest")
    require_ffmpeg()
    key = resolve_streamer(cfg, args.streamer)
    if key is None:
        sys.exit(f"Unknown streamer '{args.streamer}'. Known: {', '.join(cfg['streamers'])}")
    args.streamer = key
    if args.url and not args.url.lower().startswith(("http://", "https://")):
        sys.exit(f"'{args.url}' is not a link. Paste the full VOD address, starting with https://")
    profile = cfg["streamers"][args.streamer]

    if args.preview_only:
        vod = Path(args.preview_only)
    else:
        vods = get_path(cfg, "vods")
        vod = next_free_name(vods, f"{args.streamer}_{dt.date.today().isoformat()}")
        url = profile["channel_url"] if args.latest else args.url
        download(url, vod, args.max_hours, args.latest, log)
        log.info("Saved %s (%.1f min)", vod, probe_duration(vod) / 60)

    make_previews(vod, args.streamer, profile, log)
    print(f"\nNext: python 2_analyze.py --input {vod.relative_to(ROOT) if vod.is_relative_to(ROOT) else vod}")


if __name__ == "__main__":
    main()
