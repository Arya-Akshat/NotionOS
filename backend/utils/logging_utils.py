import asyncio
import json
from datetime import datetime
from database import SessionLocal
from models.logs import ToolCallLog, AgentRun

# Globals for WebSocket broadcast
connected_clients = set()
app_loop = None

def set_app_loop(loop):
    global app_loop
    app_loop = loop

async def broadcast(message: dict):
    """Internal helper to send a JSON message to all connected WebSocket clients."""
    if not connected_clients:
        return
    
    dead_clients = set()
    payload = json.dumps(message)
    
    for client in connected_clients:
        try:
            await client.send_text(payload)
        except Exception:
            dead_clients.add(client)
            
    for dead in dead_clients:
        connected_clients.discard(dead)

def dispatch_broadcast(message: dict):
    """
    Safely dispatches a broadcast task to the main event loop.
    Works from both main thread and worker threads.
    """
    if app_loop is None:
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
            task = asyncio.create_task(broadcast(message))
            task.add_done_callback(_on_done)
        else:
            future = asyncio.run_coroutine_threadsafe(broadcast(message), app_loop)
            future.add_done_callback(_on_done)
    except Exception as e:
        print(f"[WS] Critical dispatch error: {e}")

def _broadcast_event(event_type: str, data: dict):
    """Wrapper to broadcast a standard event structure."""
    dispatch_broadcast({"type": event_type, **data})

def log_tool_call(agent_run_id: int, tool_name: str, tool_input: dict, result: dict):
    """Writes a single tool-call record and broadcasts the update."""
    db = SessionLocal()
    try:
        status = "success" if result.get("success") else "failed"
        entry = ToolCallLog(
            agent_run_id=agent_run_id,
            tool_name=tool_name,
            tool_input=tool_input,
            status=status,
            tool_output=result.get("data"),
            error_message=result.get("error"),
            duration_ms=result.get("duration_ms"),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        
        _broadcast_event("tool_call_logged", {
            "run_id": agent_run_id,
            "log_id": entry.id,
            "tool_name": tool_name,
            "status": status,
        })
    except Exception as e:
        print(f"[DB] Failed to log tool call: {e}")
    finally:
        db.close()
