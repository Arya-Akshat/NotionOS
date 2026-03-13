"""
NotionOS Backend – FastAPI Application
Provides REST API endpoints and WebSocket for real-time log streaming.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Set

from backend.database import engine, Base, get_db
from backend.models.logs import AgentRun, ToolCallLog
from backend.workers.notion_watcher import watch_notion


# ---------------------------------------------------------------------------
# Global app loop reference for thread-safe dispatch
# ---------------------------------------------------------------------------
app_loop = None


# ---------------------------------------------------------------------------
# Lifespan – start the Notion watcher on server boot
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_loop
    app_loop = asyncio.get_running_loop()
    
    # Create tables on startup
    Base.metadata.create_all(bind=engine)
    # Launch background watcher
    task = asyncio.create_task(watch_notion(poll_interval=10))
    yield
    task.cancel()


app = FastAPI(
    title="NotionOS Backend",
    description="AI Agent Engine for Notion",
    lifespan=lifespan,
)

# CORS for the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # TODO: Use env for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "NotionOS Backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    """Return all agent runs, newest first."""
    runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "notion_task_id": r.notion_task_id,
            "status": r.status,
            "goal": r.goal,
            "execution_plan": r.execution_plan,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in runs
    ]


@app.get("/api/runs/{run_id}/logs")
def get_run_logs(run_id: int, db: Session = Depends(get_db)):
    """Return tool-call logs for a specific agent run."""
    logs = (
        db.query(ToolCallLog)
        .filter(ToolCallLog.agent_run_id == run_id)
        .order_by(ToolCallLog.created_at)
        .all()
    )
    return [
        {
            "id": l.id,
            "tool_name": l.tool_name,
            "tool_input": l.tool_input,
            "status": l.status,
            "tool_output": l.tool_output,
            "error_message": l.error_message,
            "duration_ms": l.duration_ms,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: int, db: Session = Depends(get_db)):
    """Delete an agent run and all associated tool-call logs."""
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    db.query(ToolCallLog).filter(ToolCallLog.agent_run_id == run_id).delete()
    db.delete(run)
    db.commit()

    _broadcast_event_payload = {"type": "run_deleted", "run_id": run_id}
    dispatch_broadcast(_broadcast_event_payload)

    return {"success": True, "run_id": run_id}


# ---------------------------------------------------------------------------
# WebSocket – streams new agent-run updates to the dashboard
# ---------------------------------------------------------------------------

connected_clients: Set[WebSocket] = set()

@app.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            # Client can send heartbeat messages if needed
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(ws)
    except Exception:
        connected_clients.discard(ws)

async def broadcast(message: dict):
    """Utility to push a message to all connected dashboard clients."""
    if not connected_clients:
        return
    
    payload = json.dumps(message)
    # Create a copy of the set to iterate safely without mutation errors
    clients_to_notify = list(connected_clients)
    
    for ws in clients_to_notify:
        try:
            await ws.send_text(payload)
        except Exception:
            connected_clients.discard(ws)


def dispatch_broadcast(message: dict):
    """
    Thread-safe dispatcher for WebSocket broadcasts.
    Can be called from the main async loop or worker threads.
    """
    global app_loop
    if app_loop is None:
        print("[WS] Cannot dispatch: app_loop not initialized.")
        return
    
    if app_loop.is_closed():
        print("[WS] Cannot dispatch: app_loop is closed.")
        return

    def _on_done(fut):
        try:
            fut.result()
        except Exception as e:
            print(f"[WS] Broadcast task failed: {e}")

    try:
        import threading
        if threading.current_thread() is threading.main_thread():
            # Already on the main thread loop
            task = asyncio.create_task(broadcast(message))
            task.add_done_callback(_on_done)
        else:
            # Called from a worker thread
            future = asyncio.run_coroutine_threadsafe(broadcast(message), app_loop)
            future.add_done_callback(_on_done)
    except Exception as e:
        print(f"[WS] Critical dispatch error: {e}")
