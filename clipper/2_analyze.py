"""Step 2: transcribe a VOD and score 60-second windows by "hype".

Outputs (in ./analysis):
  <vod>_analyzed.json  ranked candidate windows with transcript text: this is what Claude reads
  <vod>_words.json     every word with start/end times: 3_batch_render.py uses it for captions

Usage:
  python 2_analyze.py --input vods/kai_2026-11-19.mp4 [--model small] [--language en]
"""
from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path

import numpy as np

from common import fmt_time, get_path, load_config, probe_duration, require_ffmpeg, run, setup_logging

SR = 16000


def extract_wav(vod: Path, wav: Path, log) -> None:
    if wav.exists() and wav.stat().st_mtime > vod.stat().st_mtime:
        log.info("Reusing %s", wav.name)
        return
    log.info("Extracting 16 kHz mono WAV ...")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(vod), "-vn", "-ac", "1", "-ar", str(SR),
         "-c:a", "pcm_s16le", str(wav)])


def rms_curve(wav: Path, win_s: float, hop_s: float) -> np.ndarray:
    """RMS level in dBFS for sliding windows (read in chunks so long VODs fit in memory)."""
    win, hop = int(win_s * SR), int(hop_s * SR)
    levels = []
    carry = np.zeros(0, dtype=np.float32)
    with wave.open(str(wav), "rb") as w:
        while True:
            raw = w.readframes(SR * 600)
            if not raw:
                break
            data = np.concatenate([carry, np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0])
            n = (len(data) - win) // hop + 1 if len(data) >= win else 0
            for i in range(n):
                seg = data[i * hop: i * hop + win]
                levels.append(np.sqrt(np.mean(seg * seg) + 1e-12))
            carry = data[n * hop:]
    return 20 * np.log10(np.array(levels) + 1e-9)


def spike_scores(db: np.ndarray, hop_s: float, baseline_min: float) -> np.ndarray:
    """How far each 2 s window sits above the local loudness baseline (robust z-score)."""
    half = max(1, int(baseline_min * 60 / hop_s / 2))
    z = np.zeros_like(db)
    for i in range(len(db)):
        ref = db[max(0, i - half): i + half + 1]
        med = np.median(ref)
        mad = np.median(np.abs(ref - med)) * 1.4826 + 0.5
        z[i] = (db[i] - med) / mad
    return np.clip(z, -12, 12)  # cap so one blast can't drown out everything else


def transcribe(wav: Path, model_name: str, language: str | None, log) -> list[dict]:
    from faster_whisper import WhisperModel
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    device, compute = ("cuda", "float16") if cuda else ("cpu", "int8")
    log.info("Whisper model=%s device=%s compute=%s", model_name, device, compute)
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segments, info = model.transcribe(str(wav), language=language, word_timestamps=True,
                                      vad_filter=True, beam_size=1,
                                      condition_on_previous_text=False)
    log.info("Language: %s (p=%.2f), audio %.0f min", info.language, info.language_probability,
             info.duration / 60)
    words, last_report = [], time.time()
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"s": round(w.start, 2), "e": round(w.end, 2), "w": text})
        if time.time() - last_report > 30:
            log.info("  transcribed up to %s", fmt_time(seg.end))
            last_report = time.time()
    return words


def score_windows(words: list[dict], z: np.ndarray, db: np.ndarray, duration: float, a: dict) -> list[dict]:
    hop = a["rms_hop_seconds"]
    win, step = a["window_seconds"], a["window_step_seconds"]
    hype = [h.lower() for h in a["hype_words"]]
    starts = np.array([w["s"] for w in words]) if words else np.zeros(0)
    out = []
    t = 0.0
    while t + 20 <= duration:
        end = min(t + win, duration)
        i0, i1 = int(t / hop), max(int(t / hop) + 1, int(end / hop))
        zs = z[i0:i1]
        if len(zs) == 0:
            break
        lo, hi = np.searchsorted(starts, t), np.searchsorted(starts, end)
        ws = words[lo:hi]
        text = " ".join(w["w"] for w in ws)
        low = f" {text.lower()} "
        hype_hits = sum(low.count(f" {h} ") + low.count(f" {h}!") + low.count(f" {h},") for h in hype)
        excl = text.count("!")
        wps = len(ws) / max(1.0, end - t)
        peak_i = int(np.argmax(zs))
        top3 = float(np.mean(np.sort(zs)[-3:]))
        score = (1.0 * max(0.0, float(zs[peak_i])) + 1.2 * max(0.0, top3)
                 + 0.6 * min(hype_hits, 10) + 0.3 * min(excl, 10) + 1.5 * min(wps, 4.0))
        out.append({
            "start": round(t, 1), "end": round(end, 1),
            "start_hms": fmt_time(t), "end_hms": fmt_time(end),
            "hype_score": round(score, 2),
            "peak_time": round(t + peak_i * hop, 1), "peak_hms": fmt_time(t + peak_i * hop),
            "peak_spike_z": round(float(zs[peak_i]), 2), "top3_spike_z": round(top3, 2),
            "peak_db": round(float(db[i0 + peak_i]), 1),
            "hype_word_hits": hype_hits, "words_per_sec": round(wps, 2),
            "transcript": text,
        })
        t += step
    return out


def pick_non_overlapping(windows: list[dict], n: int, min_sep: float) -> list[dict]:
    chosen = []
    for w in sorted(windows, key=lambda x: x["hype_score"], reverse=True):
        if all(abs(w["start"] - c["start"]) >= min_sep for c in chosen):
            chosen.append(w)
        if len(chosen) >= n:
            break
    for rank, w in enumerate(chosen, 1):
        w["rank"] = rank
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="path to the VOD mp4")
    ap.add_argument("--model", default=None, help="whisper model: tiny/base/small/medium/large-v3")
    ap.add_argument("--language", default=None, help="force language code, e.g. en")
    ap.add_argument("--skip-transcribe", action="store_true", help="audio-only scoring (fast)")
    args = ap.parse_args()

    cfg = load_config()
    log = setup_logging(cfg, "analyze")
    require_ffmpeg()
    a = cfg["analysis"]
    vod = Path(args.input).resolve()
    adir = get_path(cfg, "analysis")
    wav = adir / f"{vod.stem}.wav"
    words_path = adir / f"{vod.stem}_words.json"

    duration = probe_duration(vod)
    extract_wav(vod, wav, log)
    log.info("Scoring loudness in %.0fs windows ...", a["rms_window_seconds"])
    db = rms_curve(wav, a["rms_window_seconds"], a["rms_hop_seconds"])
    z = spike_scores(db, a["rms_hop_seconds"], a["baseline_minutes"])

    if args.skip_transcribe:
        words = []
    elif words_path.exists() and words_path.stat().st_mtime > vod.stat().st_mtime:
        log.info("Reusing transcript %s", words_path.name)
        words = json.loads(words_path.read_text(encoding="utf-8"))["words"]
    else:
        t0 = time.time()
        words = transcribe(wav, args.model or a["whisper_model"], args.language, log)
        log.info("Transcribed %d words in %.1f min", len(words), (time.time() - t0) / 60)
        words_path.write_text(json.dumps({"vod_file": vod.name, "words": words}), encoding="utf-8")

    windows = score_windows(words, z, db, duration, a)
    top = pick_non_overlapping(windows, a["top_windows"], min_sep=a["window_seconds"] * 0.75)
    result = {
        "vod_file": vod.name,
        "duration_s": round(duration, 1), "duration_hms": fmt_time(duration),
        "words_file": words_path.name,
        "how_to_read": ("Windows are ranked by hype_score (loudness spikes + hype words + speech rate). "
                        "peak_hms is the loudest 2-second moment: a good place to look for the clip start. "
                        "Pick clips per CLAUDE.md and write them to cutlist.csv."),
        "candidates": top,
    }
    out = adir / f"{vod.stem}_analyzed.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("Wrote %s with %d candidate windows", out, len(top))
    for w in top[:10]:
        log.info("  #%d %s-%s score %.1f peak %s | %s", w["rank"], w["start_hms"][:8], w["end_hms"][:8],
                 w["hype_score"], w["peak_hms"][:8], w["transcript"][:80])
    try:
        wav.unlink()  # big file, no longer needed
    except OSError:
        pass


if __name__ == "__main__":
    main()
