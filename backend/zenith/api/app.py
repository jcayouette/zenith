from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from zenith import __version__
from zenith.api.routes import archive, live, processed, settings, status
from zenith.capture.service import CaptureService, LiveHub
from zenith.paths import FRONTEND_DIST, ensure_data_dir

_DEV_LANDING = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Zenith</title>
    <style>
      body { font-family: Outfit, system-ui, sans-serif; background:#070b14; color:#e8eef8;
             max-width: 40rem; margin: 12vh auto; padding: 0 1.5rem; }
      a { color:#7dd3fc; }
      code { color:#f3c16b; }
    </style>
  </head>
  <body>
    <h1>Zenith</h1>
    <p>The API is running. The UI is not built yet.</p>
    <ul>
      <li>Dev UI: <a href="http://127.0.0.1:5173/">http://127.0.0.1:5173/</a></li>
      <li>API docs: <a href="/docs">/docs</a></li>
      <li>Health: <a href="/api/health">/api/health</a></li>
    </ul>
    <p>Build the frontend with <code>npm run build</code> in <code>frontend/</code>, then restart Zenith to serve the app here.</p>
  </body>
</html>
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_data_dir()
    hub = LiveHub()
    capture = CaptureService(hub)
    app.state.hub = hub
    app.state.capture = capture
    capture.start()
    yield
    await capture.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Zenith", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(status.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(live.router, prefix="/api")
    app.include_router(archive.router, prefix="/api")
    app.include_router(processed.router, prefix="/api")
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    assets = FRONTEND_DIST / "assets"
    index = FRONTEND_DIST / "index.html"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    if index.is_file():
        @app.get("/")
        def spa_root():
            return FileResponse(index)

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            candidate = FRONTEND_DIST / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)
        return

    @app.get("/")
    def dev_root():
        return HTMLResponse(_DEV_LANDING)


app = create_app()
