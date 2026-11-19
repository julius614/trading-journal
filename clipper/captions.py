"""Build .ass subtitle files: word-highlight captions plus the 3-second hook banner."""
from __future__ import annotations

from pathlib import Path

# ASS colours are &HAABBGGRR (alpha 00 = opaque).
COLORS = {
    "white": "&H00FFFFFF", "black": "&H00000000", "yellow": "&H0000F0FF",
    "cyan": "&H00FFFF00", "lime": "&H0000FF7F", "red": "&H003030FF",
    "orange": "&H0000A5FF", "pink": "&H00B469FF",
}


def ass_color(name: str) -> str:
    if name.startswith("&H"):
        return name
    if name.startswith("#") and len(name) == 7:  # #RRGGBB
        r, g, b = name[1:3], name[3:5], name[5:7]
        return f"&H00{b}{g}{r}".upper()
    return COLORS[name.lower()]


def ass_ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    cs = int(round((s - int(s)) * 100))
    if cs == 100:
        cs = 99
    return f"{h:d}:{m:02d}:{int(s):02d}.{cs:02d}"


def esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[dict], per_line: int, max_gap: float) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= per_line or w["s"] - cur[-1]["e"] > max_gap):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def measure_text(text: str, font_size: int, font_file: str | None) -> float:
    """Pixel width of text. Uses Pillow + the font file if available, else an estimate."""
    if font_file:
        try:
            from PIL import ImageFont
            return ImageFont.truetype(font_file, font_size).getlength(text)
        except Exception:
            pass
    return len(text) * font_size * 0.66


def rounded_rect(w: float, h: float, r: float) -> str:
    """ASS vector drawing (\\p1) of a rounded rectangle with its top-left at 0,0."""
    r = min(r, h / 2, w / 2)
    k = r * 0.4477  # bezier handle offset for a quarter circle
    p = lambda v: f"{v:.0f}"  # noqa: E731
    return (f"m {p(r)} 0 l {p(w - r)} 0 b {p(w - k)} 0 {p(w)} {p(k)} {p(w)} {p(r)} "
            f"l {p(w)} {p(h - r)} b {p(w)} {p(h - k)} {p(w - k)} {p(h)} {p(w - r)} {p(h)} "
            f"l {p(r)} {p(h)} b {p(k)} {p(h)} 0 {p(h - k)} 0 {p(h - r)} "
            f"l 0 {p(r)} b 0 {p(k)} {p(k)} 0 {p(r)} 0")


def build_ass(words: list[dict], clip_len: float, hook_text: str, rs: dict, highlight: str,
              out_path: Path, font_file: str | None = None) -> Path:
    """words: [{'s','e','w'}] with times relative to the clip start (0 = first frame)."""
    W, H = (int(v) for v in rs["resolution"].split("x"))
    c, hk = rs["captions"], rs["hook"]
    base, hi = ass_color(c["base_color"]), ass_color(highlight)
    font = c["font_name"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{c['font_size']},{base},{base},&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,{c['outline']},{c['shadow']},5,40,40,0,1
Style: HookBox,{font},{hk['font_size']},{ass_color(hk['box_color'])},{ass_color(hk['box_color'])},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: HookText,{font},{hk['font_size']},{ass_color(hk['text_color'])},{ass_color(hk['text_color'])},&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,8,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []

    # Captions: one event per word so the active word is highlighted.
    cy = c["y"]
    for chunk in chunk_words(words, c["words_per_line"], c["max_gap_seconds"]):
        tokens = [esc(w["w"].upper() if c["uppercase"] else w["w"]) for w in chunk]
        for i, w in enumerate(chunk):
            start = w["s"]
            end = chunk[i + 1]["s"] if i + 1 < len(chunk) else max(w["e"], w["s"] + 0.25)
            start, end = max(0.0, start), min(clip_len, end)
            if end <= start:
                continue
            parts = [(f"{{\\c{hi}\\fscx108\\fscy108}}{t}{{\\c{base}\\fscx100\\fscy100}}" if j == i else t)
                     for j, t in enumerate(tokens)]
            lines.append(f"Dialogue: 0,{ass_ts(start)},{ass_ts(end)},Caption,,0,0,0,,"
                         f"{{\\an5\\pos({W // 2},{cy})}}{' '.join(parts)}")

    # Hook banner: rounded box (vector drawing) + text, top-anchored at hook y.
    hook = esc(hook_text.strip().upper())[: hk["max_chars"]]
    if hook:
        tw = measure_text(hook, hk["font_size"], font_file) + 2  # +spacing
        max_tw = W - 40 - 2 * hk["box_padding_x"]
        scale = min(1.0, max_tw / tw)  # squeeze long hooks to fit the frame
        bw = tw * scale + 2 * hk["box_padding_x"]
        bh = hk["font_size"] * 1.15 + 2 * hk["box_padding_y"]
        bx, by = (W - bw) / 2, hk["y"]
        fade = "\\fad(120,180)"
        t0, t1 = ass_ts(hk["start"]), ass_ts(min(hk["end"], clip_len))
        lines.append(f"Dialogue: 1,{t0},{t1},HookBox,,0,0,0,,"
                     f"{{\\an7\\pos({bx:.0f},{by:.0f}){fade}\\p1}}{rounded_rect(bw, bh, hk['corner_radius'])}{{\\p0}}")
        lines.append(f"Dialogue: 2,{t0},{t1},HookText,,0,0,0,,"
                     f"{{\\an8\\pos({W // 2},{by + hk['box_padding_y']:.0f}){fade}"
                     f"\\fscx{scale * 100:.0f}\\fscy100\\q2}}{hook}")

    out_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out_path
