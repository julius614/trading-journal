"""Shared helpers for the clipper pipeline: config, paths, time parsing, ffmpeg."""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.json"
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)


def get_path(cfg: dict, key: str) -> Path:
    """Resolve a path from config['paths'] relative to the clipper folder."""
    p = Path(cfg["paths"][key])
    if not p.is_absolute():
        p = ROOT / p
    if key in ("vods", "analysis", "output", "logs", "archive"):
        p.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging(cfg: dict, name: str) -> logging.Logger:
    log_dir = get_path(cfg, "logs")
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(
                f"'{tool}' was not found on PATH. On Windows run: winget install Gyan.FFmpeg "
                "and then open a new PowerShell window."
            )


def run(cmd: list[str], cwd: str | Path | None = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command; raise RuntimeError with the tail of stderr on failure."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2500:]
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd[:6])} ...\n{tail}")
    return proc


def probe_duration(path: str | Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)]).stdout.strip()
    return float(out)


def probe_video_size(path: str | Path) -> tuple[int, int]:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height", "-of", "csv=p=0", str(path)]).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def parse_time(value: str | float | int) -> float:
    """Accept seconds ('754.2'), 'MM:SS(.ms)' or 'HH:MM:SS(.ms)'."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        raise ValueError("empty time value")
    if ":" not in s:
        return float(s)
    parts = [float(p) for p in s.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"bad time value: {value!r}")


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


_CROP_RE = re.compile(r"^\s*(\d+):(\d+):(\d+):(\d+)\s*$")


def parse_crop(crop: str) -> tuple[int, int, int, int]:
    """'w:h:x:y' -> (w, h, x, y)."""
    m = _CROP_RE.match(crop or "")
    if not m:
        raise ValueError(f"crop must look like 'w:h:x:y', got {crop!r}")
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def check_crop_fits(crop: str, src_w: int, src_h: int) -> None:
    w, h, x, y = parse_crop(crop)
    if x + w > src_w or y + h > src_h:
        raise ValueError(f"crop {crop} goes outside the {src_w}x{src_h} source frame")


def resolve_streamer(cfg: dict, name: str) -> str | None:
    """Case-insensitive lookup by key or alias: 'SPEED', 'IShowSpeed' -> 'speed'."""
    want = name.strip().lower().replace(" ", "")
    for key, prof in cfg["streamers"].items():
        names = [key] + prof.get("aliases", [])
        if want in (n.lower().replace(" ", "") for n in names):
            return key
    return None


def find_analysis_words(cfg: dict, vod_file: str | Path) -> Path:
    return get_path(cfg, "analysis") / f"{Path(vod_file).stem}_words.json"


def resolve_vod(cfg: dict, vod_file: str) -> Path:
    p = Path(vod_file)
    if p.is_absolute() and p.exists():
        return p
    for candidate in (ROOT / p, get_path(cfg, "vods") / p.name):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"VOD not found: {vod_file}")
