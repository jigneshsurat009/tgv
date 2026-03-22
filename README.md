# Telegram Video Watermark Bot

This build is focused on the simplest reliable flow:
- send or forward a video to the bot
- choose a preset, or use manual setup
- optionally preview first
- bot watermarks the video and sends it back

## Included features
- direct Telegram upload / forwarded video handling
- select all videos or selected videos only
- saved watermark presets
- apply same preset to all selected videos
- per-video preset override
- manual custom setup
- exact time range input:
  - `full`
  - `00:00 02:00`
  - `01:00 10:00`
  - `18:00 END`
- random anywhere watermark position
- smooth moving watermark position
- preview first
- resume failed batch
- job history
- live text progress bar during ffmpeg processing
- SQLite-backed state and batch records

## Manual custom flow
1. Send or forward a video.
2. Choose `Watermark All Videos` or `Select Videos`.
3. Choose `Manual Custom Time + Position`.
4. Pick watermark type.
5. Pick position mode.
6. Pick strength.
7. Send the range as text:
   - `full`
   - `00:00 02:00`
   - `01:00 10:00`
   - `18:00 END`
8. Choose preview or apply.

## Built-in presets
- Full Fixed
- First 2 Min
- After 3 Min
- Last 2 Min
- Every 3 Min
- Random 5 Times
- Mixed Smart

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Install `ffmpeg` and `ffprobe` first and make sure both are in PATH.

## Important notes
- Forwarded Telegram video files work the same as uploaded video files.
- If `WATERMARK_IMAGE` is empty, image mode falls back to text mode.
- Job history and resume state are stored in SQLite under `./data`.
- Temporary processing files are stored in `./tmp`.

## .env notes
Set these at minimum:
- `BOT_TOKEN`
- `WATERMARK_TEXT`
- optionally `WATERMARK_IMAGE`
- optionally `FFMPEG_BIN` and `FFPROBE_BIN`
