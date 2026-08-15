from __future__ import annotations

import base64

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

router = APIRouter(tags=["live"])


@router.get("/live.jpg")
def live_jpeg(request: Request):
    jpeg = request.app.state.hub.jpeg
    if not jpeg:
        return Response(status_code=503)
    return Response(content=jpeg, media_type="image/jpeg")


@router.websocket("/ws/live")
async def live_ws(ws: WebSocket):
    await ws.accept()
    hub = ws.app.state.hub
    queue = hub.subscribe()
    try:
        if hub.jpeg:
            await ws.send_json(_packet(hub.jpeg, hub.telemetry.as_dict()))
        while True:
            payload = await queue.get()
            await ws.send_json(_packet(payload["jpeg"], payload["telemetry"]))
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)


def _packet(jpeg: bytes, telemetry: dict) -> dict:
    return {
        "image": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"),
        "telemetry": telemetry,
    }
