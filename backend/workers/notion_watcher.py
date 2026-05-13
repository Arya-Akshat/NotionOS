"""
Notion Watcher – Background worker that polls a Notion database every 10 seconds
for tasks where AgentStatus == "Pending" and dispatches them to the agent workflow.
"""

import logging
import asyncio
from database import SessionLocal
from models.logs import AgentRun
from tools.notion_tool import read_notion_tasks, update_notion_task_status, get_approval_status
from workflows.task_agent import agent_app
from notion_mcp.client import mcp_client
from config import config

# Track active Notion Page IDs to prevent redundant processing
PROCESSING_TASK_IDS = set()

async def resume_task(run: AgentRun):
    """Resumes an approved task from where it left off."""
    if run.notion_task_id in PROCESSING_TASK_IDS:
        return
    PROCESSING_TASK_IDS.add(run.notion_task_id)
    
    print(f"[Watcher] Resuming task run {run.id} for page {run.notion_task_id}")
    try:
        # Reconstruct state from DB
        state = {
            "task_id": run.notion_task_id,
            "task_text": "", 
            "status": "EXECUTING",
            "goal": run.goal or "",
            "execution_plan": run.execution_plan or [],
            "current_step": run.current_step or 0,
            "tool_outputs": run.tool_outputs or {},
            "errors": run.errors or [],
            "workflow_id": run.id,
            "messages": [],
        }
        await agent_app.ainvoke(state)
    except Exception as e:
        print(f"[Watcher] Resume failed for run {run.id}: {e}")
        from tools.notion_tool import update_notion_task_status
        await update_notion_task_status(run.notion_task_id, "FAILED")
    finally:
        # Only remove if the run is finished (completed or failed)
        # Note: In this simple implementation, ainvoke finishes when the graph hits END
        PROCESSING_TASK_IDS.discard(run.notion_task_id)


async def process_task(task: dict, run_id: int):
    """Run the LangGraph agent for a single Notion task using an existing run_id."""
    page_id = task["page_id"]
    title = task.get("title", "")
    goal = task.get("goal", "")
    task_text = f"{title}. {goal}" if goal else title

    print(f"[Watcher] Starting execution for run {run_id}: {title} ({page_id})")

    try:
        # Reset Notion page for a fresh run
        from tools.notion_tool import write_run_separator
        await write_run_separator(page_id)
        
        # 2. Trigger LangGraph workflow
        initial_state = {
            "task_id": page_id,
            "task_text": task_text,
            "status": "PLANNING",
            "goal": goal or title,
            "execution_plan": [],
            "current_step": 0,
            "tool_outputs": {},
            "errors": [],
            "workflow_id": run_id,
            "messages": [],
        }
        await agent_app.ainvoke(initial_state)
    except Exception as e:
        print(f"[Watcher] Agent execution failed for run {run_id}: {e}")
        from tools.notion_tool import update_notion_task_status
        await update_notion_task_status(page_id, "FAILED")
        db = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.status = "FAILED"
                db.commit()
        finally:
            db.close()
    finally:
        PROCESSING_TASK_IDS.discard(page_id)


async def watch_notion(poll_interval: int = 10):
    """Infinite polling loop with synchronous locking."""
    print(f"[Watcher] Starting Notion watcher (poll every {poll_interval}s)...")
    while True:
        try:
            # 1. Cleanup orphaned 'PLANNING' tasks (stuck for > 2 mins)
            db = SessionLocal()
            try:
                from datetime import datetime, timedelta
                timeout = datetime.utcnow() - timedelta(minutes=2)
                orphans = db.query(AgentRun).filter(
                    AgentRun.status == "PLANNING",
                    AgentRun.created_at < timeout
                ).all()
                for orphan in orphans:
                    print(f"[Watcher] Cleaning up orphaned planning task {orphan.id}")
                    db.delete(orphan)
                db.commit()
            finally:
                db.close()

            # 2. Poll for pending tasks
            res = read_notion_tasks()
            if res.get("success"):
                for task in res.get("data", []):
                    page_id = task["page_id"]
                    title = task.get("title", "")
                    goal = task.get("goal", "")
                    
                    # GATE 1: In-memory set
                    if page_id in PROCESSING_TASK_IDS:
                        continue
                        
                    # GATE 2: Database check (Synchronous)
                    db = SessionLocal()
                    try:
                        existing = db.query(AgentRun).filter(
                            AgentRun.notion_task_id == page_id,
                            AgentRun.status.notin_(["FAILED", "REJECTED", "COMPLETED"])
                        ).first()
                        if existing:
                            continue
                        
                        # STEP B: Create the AgentRun row RIGHT NOW before dispatching
                        new_run = AgentRun(
                            notion_task_id=page_id,
                            status="PLANNING",
                            goal=goal or title
                        )
                        db.add(new_run)
                        db.commit()
                        db.refresh(new_run)
                        run_id = new_run.id
                    finally:
                        db.close()

                    # LOCK: Add to processing set
                    PROCESSING_TASK_IDS.add(page_id)
                    
                    # STEP C: Update Notion status to "In Progress" RIGHT NOW synchronously
                    await update_notion_task_status(page_id, "In Progress")
                    
                    # STEP D: NOW dispatch to background, passing run_id
                    print(f"[Watcher] Dispatched task {run_id} for {page_id}")
                    asyncio.create_task(process_task(task, run_id))
            
            # 3. Check for resumptions
            db = SessionLocal()
            try:
                executing_runs = db.query(AgentRun).filter(AgentRun.status == "EXECUTING").all()
                for run in executing_runs:
                    if run.notion_task_id not in PROCESSING_TASK_IDS:
                        asyncio.create_task(resume_task(run))
                
                # Manual Notion approvals
                waiting_runs = db.query(AgentRun).filter(AgentRun.status == "WAITING_FOR_APPROVAL").all()
                for run in waiting_runs:
                    if get_approval_status(run.notion_task_id) == "Approved":
                        from workflows.task_agent import approve_workflow
                        approve_workflow(run.id)
            finally:
                db.close()

        except Exception as e:
            print(f"[Watcher] Unexpected error in loop: {e}")

        await asyncio.sleep(poll_interval)
