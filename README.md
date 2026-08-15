# Zenith

Modern all-sky camera. Full design: [PLAN.md](PLAN.md).

## How we work

GitHub is the source of truth. Develop **on the Pi** in Cursor over SSH so you have the HQ camera, GPIO, and NVMe.

1. Clone on the Pi: `git clone git@github.com:jcayouette/zenith.git ~/zenith`
2. In Cursor: **Remote-SSH** → `acmeastro@10.0.0.52` → open `~/zenith`
3. Commit and push from that window as usual

Optional SSH config on your laptop:

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

```bash
sudo apt install python3-picamera2 python3-venv
cd ~/zenith/backend
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
cd ../frontend && npm install && npm run build
ZENITH_DATA=$HOME/zenith/data zenith --host 0.0.0.0 --port 8000
```

Open http://10.0.0.52:8000/ and set `camera.backend` to `picamera2`.
