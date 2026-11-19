"""Self-test: builds a 10 s synthetic 1080p "stream", renders it through the real
split-screen + caption + hook code, and checks the result.

Usage:  python test_pipeline.py
Look at: test_out/test_clip.mp4 and test_out/frame_*.png
"""
from __future__ import annotations

import importlib.util
import json
import random
import shutil
import sys
import wave
from pathlib import Path

import numpy as np

from common import ROOT, load_config, probe_duration, probe_video_size, require_ffmpeg, run

OUT = ROOT / "test_out"


def load_module(filename: str):
    spec = importlib.util.spec_from_file_location(filename.replace(".py", "").lstrip("0123456789_"),
                                                  ROOT / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def check(cond: bool, msg: str) -> None:
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        sys.exit(1)


def make_synthetic_vod(path: Path) -> None:
    """1920x1080 test pattern with a fake 'webcam' box top-right and a loud burst at 6-7 s."""
    run(["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=10",
         "-f", "lavfi", "-i", "color=c=0x8040c0:size=480x300:rate=30:duration=10",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=10",
         "-filter_complex",
         "[0:v][1:v]overlay=1440:0,drawtext=text='WEBCAM':x=1560:y=130:fontsize=48:fontcolor=white[v];"
         "[2:a]volume='if(between(t,6,7),1.0,0.05)':eval=frame[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-metadata", "title=SECRET SOURCE TITLE", str(path)])


def main() -> None:
    require_ffmpeg()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    print("1. Synthetic VOD")
    vod = OUT / "test_2026-01-01.mp4"
    make_synthetic_vod(vod)
    check(probe_video_size(vod) == (1920, 1080), "synthetic VOD is 1920x1080")

    print("2. Analysis maths (audio only)")
    analyze = load_module("2_analyze.py")
    wav = OUT / "test.wav"
    analyze.extract_wav(vod, wav, type("L", (), {"info": staticmethod(lambda *a: None)}))
    with wave.open(str(wav)) as w:
        check(w.getframerate() == 16000 and w.getnchannels() == 1, "WAV is 16 kHz mono")
    db = analyze.rms_curve(wav, 2.0, 1.0)
    z = analyze.spike_scores(db, 1.0, 5)
    check(5 <= int(np.argmax(z)) <= 7, f"loud burst detected near 6 s (peak window at {int(np.argmax(z))} s)")

    print("3. Render split-screen + captions + hook")
    cfg = load_config()
    cfg = json.loads(json.dumps(cfg))
    cfg["paths"] = {**cfg["paths"], "vods": str(OUT), "analysis": str(OUT), "output": str(OUT / "output")}
    cfg["streamers"]["_test"] = {"channel_url": "", "webcam_crop": "480:300:1440:0",
                                 "gameplay_crop": "1080:1080:420:0"}
    text = "bro what just happened no way chat look at this car it is flying".split()
    words = [{"s": round(0.4 + i * 0.55, 2), "e": round(0.4 + i * 0.55 + 0.45, 2), "w": t}
             for i, t in enumerate(text)]
    (OUT / "test_2026-01-01_words.json").write_text(json.dumps({"words": words}), encoding="utf-8")

    render = load_module("3_batch_render.py")
    row = {"clip_id": "test_clip", "streamer": "_test", "vod_file": str(vod), "start_time": "0",
           "end_time": "10", "hook_text": "BRO BROKE GTA 6 PHYSICS", "account_tag": "_test", "status": ""}
    clip_id, status, msg = render.render_one({"cfg": cfg, "row": row, "threads": 4})
    check(status == "DONE", f"render finished: {msg[:300]}")
    out = OUT / "output" / "_test" / "test_clip.mp4"
    check(out.exists(), f"output exists: {out.relative_to(ROOT)}")
    check(probe_video_size(out) == (1080, 1920), "output is 1080x1920")
    check(abs(probe_duration(out) - 10) < 0.3, f"duration ~10 s ({probe_duration(out):.2f})")
    tags = run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(out)]).stdout
    check("SECRET SOURCE TITLE" not in tags, "source metadata stripped")
    loud = run(["ffmpeg", "-v", "info", "-i", str(out), "-af", "ebur128", "-f", "null", "-"]).stderr
    check("I:" in loud, "audio track present and measurable")

    for t in (1.5, 5.0):
        run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1",
             str(OUT / f"frame_{t:.1f}s.png")])
    check((OUT / "frame_1.5s.png").exists(), "frames saved (1.5 s shows the hook, 5.0 s captions only)")

    print("4. Schedule maths")
    manifest = load_module("4_manifest.py")
    rng = random.Random(1)
    for _ in range(200):
        ts = manifest.post_times(4, 8 * 60, 23 * 60 + 30, 210, rng)
        assert all(b - a >= 209 for a, b in zip(ts, ts[1:])) and ts[0] >= 480 and ts[-1] <= 1410
    check(True, "200 random 4-post days all keep a >= 3.5 h gap inside 08:00-23:30")

    print(f"\nAll checks passed. Look at {OUT.relative_to(ROOT)}/frame_1.5s.png and test_clip.mp4")


if __name__ == "__main__":
    main()
