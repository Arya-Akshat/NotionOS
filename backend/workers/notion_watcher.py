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
                    
                    # STEP A: Check PROCESSING_TASK_IDS set
                    if page_id in PROCESSING_TASK_IDS:
                        continue
                        
                    # STEP B: Check DB for existing non-failed run
                    db = SessionLocal()
                    try:
                        existing = db.query(AgentRun).filter(
                            AgentRun.notion_task_id == page_id,
                            AgentRun.status.notin_(["FAILED", "REJECTED"])
                        ).first()
                        
                        if existing:
                            if existing.status == "COMPLETED":
                                await update_notion_task_status(page_id, "Done")
                            continue
                        
                        # STEP C: Add to PROCESSING_TASK_IDS immediately
                        PROCESSING_TASK_IDS.add(page_id)

                        # STEP D: Create AgentRun row RIGHT NOW synchronously
                        new_run = AgentRun(
                            notion_task_id=page_id,
                            status="PLANNING",
                            goal=title
                        )
                        db.add(new_run)
                        db.commit()
                        db.refresh(new_run)
                        run_id = new_run.id
                        print(f"[Watcher] Created run {run_id} for {page_id} synchronously.")
                    except Exception as e:
                        print(f"[Watcher] Failed to create run: {e}")
                        PROCESSING_TASK_IDS.discard(page_id)
                        continue
                    finally:
                        db.close()

                    # STEP E: Update Notion to "In Progress" RIGHT NOW
                    await update_notion_task_status(page_id, "In Progress")

                    # STEP F: NOW dispatch to workflow passing run_id
                    from workflows.task_agent import run_workflow
                    asyncio.create_task(run_workflow(page_id, title, run_id))
            
            # 3. Check for resumptions
            db = SessionLocal()
            try:
                executing_runs = db.query(AgentRun).filter(AgentRun.status == "EXECUTING").all()
                for run in executing_runs:
                    # BUG 2 FIX: Skip if already COMPLETED in DB (double check)
                    if run.status == "COMPLETED":
                        continue
                        
                    if run.notion_task_id not in PROCESSING_TASK_IDS:
                        PROCESSING_TASK_IDS.add(run.notion_task_id) # Add to lock
                        from workflows.task_agent import run_workflow
                        asyncio.create_task(run_workflow(run.notion_task_id, run.goal or "Resumed", run.id))
                
                # Manual Notion approvals
                waiting_runs = db.query(AgentRun).filter(AgentRun.status == "WAITING_FOR_APPROVAL").all()
                for run in waiting_runs:
                    if run.status == "COMPLETED": continue # Skip
                    
                    if get_approval_status(run.notion_task_id) == "Approved":
                        from workflows.task_agent import approve_workflow
                        approve_workflow(run.id)
            finally:
                db.close()

        except Exception as e:
            print(f"[Watcher] Unexpected error in loop: {e}")

        await asyncio.sleep(poll_interval)
