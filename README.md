# Zenith

All-sky camera for Raspberry Pi. Design notes: [PLAN.md](PLAN.md).

This tree is meant to run **on the Pi** (HQ / IMX477, NVMe, GPIO). Open `~/zenith` in Cursor on that machine and work there. GitHub is the source of truth.

## What you get

- **Live** — WebSocket preview, focus vs RAW, colour/exposure sliders
- **Archive** — night/day sessions, DNG/PNG, delete, RAW timelapse encode with progress
- **Processed** — keograms, startrails, timelapses under typed folders
- **Settings** — generated from the Pydantic schema
- **System** — disk, RAM, CPU, temperatures, throttle flags

API + UI share one process on port **8000**.

## Requirements

On Raspberry Pi OS:

- Python 3.11+
- `python3-picamera2` (apt) so CSI capture works
- `ffmpeg` for timelapses
- Node.js **20+** and `npm` on `PATH` (a user-local install under `~/.local` is fine)

The venv **must** use `--system-site-packages` so apt `picamera2` / `simplejpeg` are visible. Keep **NumPy 1.x** (`numpy>=1.24,<2`). Pip NumPy 2.x breaks the apt camera stack.

One Zenith process only — the HQ camera cannot be shared.

## First-time setup

```bash
sudo apt install python3-picamera2 python3-venv python3-numpy ffmpeg git

git clone git@github.com:jcayouette/zenith.git ~/zenith
cd ~/zenith

# Node 20+ (skip if `node -v` already shows v20+)
export PATH="$HOME/.local/bin:$PATH"

cd backend
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -c "import numpy; assert numpy.__version__.startswith('1.'), numpy.__version__"
pip install -e .

cd ../frontend
npm install
npm run build
```

Confirm `import picamera2` works inside the venv. If NumPy reports 2.x, do not `pip install numpy` — recreate the venv with `--system-site-packages` and use apt’s 1.24.x.

## Run

```bash
export PATH="$HOME/.local/bin:$HOME/zenith/backend/.venv/bin:$PATH"
cd ~/zenith
ZENITH_DATA=$HOME/zenith/data zenith --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000/ on the Pi, or `http://<pi-ip>:8000/` on the LAN.

Optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ZENITH_DATA` | `~/zenith/data` | Archive, processed files, `config.yaml` |
| `ZENITH_CONFIG` | `$ZENITH_DATA/config.yaml` | Settings file (gitignored) |

After UI changes, rebuild then restart:

```bash
export PATH="$HOME/.local/bin:$PATH"
cd ~/zenith/frontend && npm run build
```

Stop the running `zenith` process (`kill <pid>`, `kill -9` if it is stuck), then start it again. Do not run two copies. Disconnect the camera in Settings before unplugging CSI.

Set **latitude / longitude** (and timezone) in Settings so night dating matches the site. Night frames always save; daytime frames save when `camera.save_day` is on.

## Tests

```bash
cd ~/zenith/backend
.venv/bin/python -m unittest discover -s tests -v
```

## Camera and files

On this Pi the backend defaults to **picamera2**. Off-Pi (no Picamera2) it defaults to the **simulator**.

Science archive is **12-bit DNG** (HQ) plus a lossless RGB **PNG**. JPEG is live preview and thumbs only. Colour/gain sliders affect JPEG/PNG/thumbs; they do not stretch the DNG.

Timelapses prefer developed DNG → H.264. Outputs go to `processed/`, not mixed into the frame folders.

## Data layout

```
$ZENITH_DATA/
  config.yaml
  latest.jpg
  nights/YYYY-MM-DD/{raw,png,jpeg,thumbs}/
  days/YYYY-MM-DD/{raw,png,jpeg,thumbs}/
  processed/
    keograms/YYYY-MM-DD/
    startrails/YYYY-MM-DD/
    timelapses/YYYY-MM-DD/
    developed/YYYY-MM-DD/    # DNG→JPEG cache for ffmpeg
  products/YYYY-MM-DD/       # legacy; still listed if present
  darks/
  logs/
```

A night is sunset on date D through sunrise D+1, stored as `nights/YYYY-MM-DD`.

`data/` is gitignored. Do not commit `config.yaml`, `.env`, or captured frames.
