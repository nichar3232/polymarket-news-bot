"""
Web dashboard API server.

FastAPI application serving:
  GET  /           → dashboard HTML
  GET  /api/state  → full snapshot (REST)
  WS   /ws         → real-time updates via WebSocket

Runs on http://localhost:8080 alongside the agent in the same event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from src.api.state import agent_state


class SafeJSONEncoder(json.JSONEncoder):
    """Replace NaN/Infinity with null so the output is always valid JSON."""

    def default(self, o):
        return super().default(o)

    def encode(self, o):
        return super().encode(self._sanitize(o))

    def _sanitize(self, obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._sanitize(v) for v in obj]
        return obj


def _safe_json(obj) -> str:
    return json.dumps(obj, cls=SafeJSONEncoder)


app = FastAPI(title="Polymarket News Bot", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve the built React dashboard if it exists, otherwise redirect to dev server
DASHBOARD_DIST = Path(__file__).resolve().parent.parent.parent / "dashboard" / "dist"


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    index = DASHBOARD_DIST / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text())
    return HTMLResponse(
        content='<meta http-equiv="refresh" content="0;url=http://localhost:3000">'
        '<p>Redirecting to <a href="http://localhost:3000">dashboard dev server</a>...</p>'
    )


# Serve built static assets (JS/CSS bundles)
if DASHBOARD_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DASHBOARD_DIST / "assets")), name="assets")


@app.get("/api/state")
async def get_state() -> JSONResponse:
    return JSONResponse(agent_state.full_snapshot()["data"])


@app.get("/api/portfolio")
async def get_portfolio() -> JSONResponse:
    return JSONResponse(agent_state.portfolio_snapshot)


@app.get("/api/analyses")
async def get_analyses() -> JSONResponse:
    return JSONResponse([
        agent_state._analysis_to_dict(a)
        for a in agent_state.recent_analyses[-50:]
    ])


@app.get("/api/events")
async def get_events() -> JSONResponse:
    return JSONResponse([
        {"kind": e.kind, "message": e.message, "ts": e.timestamp}
        for e in agent_state.events[-100:]
    ])


@app.get("/api/news")
async def get_news() -> JSONResponse:
    return JSONResponse(agent_state.news_items[-50:])


@app.get("/api/calibration")
async def get_calibration() -> JSONResponse:
    from src.fusion.calibration import calibration_tracker
    return JSONResponse(calibration_tracker.to_dict())


@app.get("/api/config")
async def get_config() -> JSONResponse:
    snap = agent_state.full_snapshot().get("data", {})
    return JSONResponse(snap.get("config", {}))


@app.get("/api/ingestion")
async def get_ingestion_metrics() -> JSONResponse:
    from src.ingestion.metrics import ingestion_metrics
    return JSONResponse(ingestion_metrics.snapshot())


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    queue = agent_state.subscribe()

    try:
        # Send full initial state on connect
        await ws.send_text(_safe_json(agent_state.full_snapshot()))

        # Stream updates as they arrive
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                await ws.send_text(_safe_json(msg))
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await ws.send_text('{"type":"ping"}')
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        agent_state.unsubscribe(queue)


async def start_api_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Run uvicorn in the current event loop."""
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",   # suppress uvicorn access logs
        loop="none",           # use the existing asyncio event loop
    )
    server = uvicorn.Server(config)
    # suppress the "Started server process" banner — we log it ourselves
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    print(f"\n  Dashboard -> http://localhost:{port}\n")
    await server.serve()
