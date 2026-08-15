# Zenith

Modern all-sky camera. Full design: [PLAN.md](PLAN.md).

## How we work

GitHub is the source of truth. Develop **on the Pi** in Cursor over SSH so you have the HQ camera, GPIO, and NVMe.

1. Clone on the Pi: `git clone git@github.com:jcayouette/zenith.git ~/zenith`
2. In Cursor: **Remote-SSH** → `acmeastro@10.0.0.52` → open `~/zenith`
3. Commit and push from that window as usual

Optional SSH config on the laptop:

```
Host acmeastro
  HostName 10.0.0.52
  User acmeastro
```

Simulator-only UI work can still happen on a laptop; real capture runs on the Pi.

## Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic, Picamera2 / INDI / MQTT camera backends
- **Frontend:** React 19, TypeScript, Vite, Tailwind

## Run on the Pi

Needs Node 20+ (`npm`), `python3-picamera2`, and `ffmpeg` (for timelapses).

```bash
sudo apt install python3-picamera2 python3-venv ffmpeg
cd ~/zenith/backend
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
cd ../frontend && npm install && npm run build
ZENITH_DATA=$HOME/zenith/data zenith --host 0.0.0.0 --port 8000
```

Open http://10.0.0.52:8000/

On this Pi the camera backend defaults to **picamera2** (HQ / IMX477). Off-Pi it defaults to the simulator. Set **latitude / longitude** in Settings so day/night and night dating match the site.

Daytime frames are stored only when `camera.save_day` is on. Night frames are always archived while night capture is running.

Science archive is **DNG** (Picamera2) or lossless **PNG** (simulator). JPEG is live preview and thumbs only. Auto gain / contrast / colour stretch the live view; they do not rewrite the DNG.

## Data layout

```
$ZENITH_DATA/
  latest.jpg
  nights/YYYY-MM-DD/{raw,png,thumbs}/
  days/YYYY-MM-DD/{raw,png,thumbs}/
  products/YYYY-MM-DD/
    keogram_realtime.jpg
    keogram.jpg
    startrails.jpg
    startrails_stack.png
    mini.mp4
    timelapse.mp4
```

`raw/` holds 12-bit DNG (HQ camera) or lossless PNG. `png/` is a lossless RGB companion for timelapses. `thumbs/` are small JPEGs for the archive page.

A night is sunset on date D through sunrise D+1, stored as `nights/YYYY-MM-DD`.
