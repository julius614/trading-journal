# Clipper: instructions for Claude

This folder is a separate project from the trading journal. It turns long streamer VODs
into 9:16 split-screen clips. The repo-wide hard rules (no secrets, public repo) still apply.

## The pipeline
| Step | Command (run inside `clipper/`) | Output |
|---|---|---|
| 1 | `python 1_ingest.py --streamer kai --url <VOD_URL> [--max-hours 4]` | `vods/kai_<date>.mp4`, `preview_kai.png`, `preview_kai_boxes.png` |
| 2 | `python 2_analyze.py --input vods/kai_<date>.mp4` | `analysis/<vod>_analyzed.json`, `analysis/<vod>_words.json` |
| 3 | Claude writes `cuts/<vod_stem>.csv` (rules below); render imports it | |
| 4 | `python 3_batch_render.py` | `output/<account_tag>/<clip_id>.mp4`, status set to `DONE` |
| 5 | `python 4_manifest.py --date YYYY-MM-DD` | `upload_manifest.csv` |

Self-test: `python test_pipeline.py`.

## When the user gives a new VOD URL
1. Check `config.json` has the streamer. If not, add a profile with placeholder crops.
2. Run step 1. Open `preview_<streamer>_boxes.png` and check that the red box covers just the
   webcam and the green box covers the useful middle of the gameplay. Fix the crops in
   `config.json` (`w:h:x:y` in source pixels) and re-check with
   `python 1_ingest.py --streamer <key> --preview-only <vod>` before rendering anything.
3. Run step 2, then choose clips as below.

## Choosing clips from `<vod>_analyzed.json`
- `candidates` are 60 s windows ranked by `hype_score` (loudness spikes, hype words, speech
  rate). `peak_hms` is the loudest 2 s moment. Read the `transcript` of each window; the
  score only finds candidates, and the story decides.
- Pick the best **20-30 clips per VOD**. Skip windows that are only loud (music, alerts, an
  ad read) with no story in the transcript.
- To refine a start or end, look up exact word times in `<vod>_words.json` (`s` = start,
  `e` = end, in seconds from the VOD start).

## Strict cutlist rules
1. **Length 28-62 s.** Use 60-62 s when the story fills it (TikTok's 1-minute monetisation
   threshold), and 30-45 s for pure comedy and fails, where retention matters most. The
   renderer rejects anything outside 28-62 s.
2. **No slow intros.** Start on the exact moment of action: the scream, crash, punchline
   or first line of the argument. Never start on walking, driving around quietly, menus or
   loading screens. Usually start 0.3-1.0 s before the first word of the key line.
3. **End on the payoff.** Cut right after the punchline or reaction. Never trail off.
4. **Platform safety: no graphic violence or shootouts in the first 7 seconds.** If the
   moment is a shootout, start on the build-up line or the reaction instead. Skip clips
   whose whole point is gore. No slurs or targeted harassment anywhere in the clip.
5. **`hook_text`: 3-5 words, uppercase, curiosity-driven, true to the clip.** Examples:
   `BRO BROKE GTA 6 PHYSICS`, `INSTANT REGRET IN VICE CITY`, `HE DID NOT SEE THAT COMING`.
   No clickbait the clip doesn't pay off. Max 34 characters. Avoid commas (CSV).
6. **No overlaps.** Clips from the same VOD must not share more than 5 s of footage.
7. **One clip, one account.** Each moment goes to exactly one `account_tag` (from
   `config.json -> accounts`), matched to that account's niche. Never put the same or a
   re-cut version of the same moment on two accounts.
8. **Only clip creators who allow it.** Many streamers run clipping programmes or openly
   allow clips. If the user hasn't confirmed this for a streamer, say so once.

## Where clip rows go
- Claude writes new rows to **`cuts/<vod_stem>.csv`** (tracked in git) and pushes.
- The user's `cutlist.csv` is local only (gitignored): `3_batch_render.py` imports any new
  `clip_id` from `cuts/*.csv` into it as PENDING, then renders and marks DONE/FAILED there.
  This keeps `git pull` from ever conflicting with render status.
- Never reuse a clip_id. To change a clip that already rendered, add a new clip_id.

## cutlist.csv format
```
clip_id,streamer,vod_file,start_time,end_time,hook_text,account_tag,status
kai_1119_01,kai,kai_2026-11-19.mp4,01:12:03.4,01:13:04.9,BRO BROKE GTA 6 PHYSICS,gta_fails,PENDING
```
- `clip_id`: `<streamer>_<MMDD>_<NN>`, unique forever (it becomes the file name).
- `vod_file`: the file name in `vods/`.
- Times as `HH:MM:SS.s` from the VOD start.
- `status`: `PENDING` for new rows. The renderer sets `DONE`, `FAILED: ...` or `ERROR: ...`.
- Optional extra columns: `layout` (`split` default, or `fit` = whole frame centred on a
  blurred background, for moments where the webcam is big or moves, e.g. Ome.tv / just
  chatting), and `webcam_crop` / `gameplay_crop` to override the streamer's default crops
  for that clip. Streams change layout, so check a frame (`1_ingest.py --preview-only
  <vod> --at <minutes>`) when a clip comes from a different segment of the stream.
- Append rows. Never edit or delete `DONE` rows.
- After writing, show the user a short table (id, length, hook, account, one-line reason).

## Render facts (for answering questions)
- 1080x1920: webcam scaled to fill the top 1080x672, gameplay to fill the bottom 1080x1248.
- Captions: 4 words per line, bold uppercase, thick outline, active word highlighted, centred
  on the seam (y=672). The highlight colour is picked per clip from the pool in config.
- Hook: rounded white box at y=760, 0-3.2 s.
- Audio: loudnorm I=-14 LUFS, TP=-1.5, LRA=11. Container metadata is stripped.
- There is deliberately no "anti-duplicate" or fingerprint-evasion processing (random zoom,
  speed or colour jitter to dodge duplicate detection). Don't add it. Variety comes from
  choosing different moments, hooks and edits.
- Fonts: put a `.ttf`/`.otf` in `fonts/` and set `captions.font_name` to its family name.
