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
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from src.api.state import agent_state


app = FastAPI(title="Polymarket News Bot", docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    index = STATIC_DIR / "index.html"
    return HTMLResponse(content=index.read_text())


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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    queue = agent_state.subscribe()

    try:
        # Send full initial state on connect
        await ws.send_text(json.dumps(agent_state.full_snapshot()))

        # Stream updates as they arrive
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                await ws.send_text(json.dumps(msg))
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await ws.send_text(json.dumps({"type": "ping"}))
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
    print(f"\n  Dashboard → http://localhost:{port}\n")
    await server.serve()
