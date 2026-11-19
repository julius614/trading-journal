# Clipper

Turns long streamer VODs into 1080x1920 split-screen clips (webcam on top, gameplay below)
with word-by-word captions, a 3-second hook banner and -14 LUFS audio.

## One-time setup on Windows (PowerShell)

1. Install Python 3.11 or newer, FFmpeg and Git (skip any you already have):
   ```
   winget install Python.Python.3.12
   winget install Gyan.FFmpeg
   ```
   Close PowerShell and open a new window afterwards so it finds them.
2. Go to the folder and create the virtual environment:
   ```
   cd $HOME\trading-journal\clipper
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   If PowerShell refuses to run `Activate.ps1`, run this once, then try again:
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
3. Test it:
   ```
   python test_pipeline.py
   ```
   It should end with `All checks passed`. Open `test_out\frame_1.5s.png` to see the layout.
4. Optional: copy a bold font such as Montserrat ExtraBold `.ttf` into `fonts\` and set
   `"font_name"` in `config.json` to its name. Otherwise Arial Black is used.

Every new PowerShell session: `cd` into the folder and run `.\venv\Scripts\Activate.ps1`.

## Daily use
```
python 1_ingest.py --streamer kai --url "https://www.twitch.tv/videos/123456789" --max-hours 4
python 2_analyze.py --input vods\kai_2026-11-19.mp4
# ask Claude: "pick the clips from analysis\kai_2026-11-19_analyzed.json"
python 3_batch_render.py
python 4_manifest.py --date 2026-11-20
```
- After step 1, open `preview_kai_boxes.png`. The red box must cover the webcam and the
  green box the gameplay. If not, fix `webcam_crop` / `gameplay_crop` in `config.json`.
- Step 2 on CPU takes roughly 15-30 minutes per hour of VOD with the `small` model. Use
  `--model base` for faster and rougher results.
- With an NVIDIA GPU, set `"video_encoder": "h264_nvenc"` in `config.json` for faster renders.

See `CLAUDE.md` for the clip selection rules.
