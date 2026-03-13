"""
Notion Watcher – Background worker that polls a Notion database every 10 seconds
for tasks where AgentStatus == "Pending" and dispatches them to the agent workflow.
"""

import asyncio
from backend.tools.notion_tool import read_notion_tasks, update_notion_task_status
from backend.workflows.task_agent import agent_app


async def process_task(task: dict):
    """Run the LangGraph agent for a single Notion task."""
    page_id = task["page_id"]
    title = task.get("title", "")
    goal = task.get("goal", "")
    task_text = f"{title}. {goal}" if goal else title

    print(f"[Watcher] Processing task: {title} ({page_id})")

    # Mark as In Progress so we don't pick it up again
    update_notion_task_status(page_id, "In Progress")

    # Build initial agent state
    initial_state = {
        "task_id": page_id,
        "original_text": task_text,
        "status": "PENDING",
        "goal": "",
        "execution_plan": [],
        "current_step": 0,
        "tool_outputs": {},
        "errors": [],
        "messages": [],
    }

    try:
        # LangGraph invoke is synchronous – run in executor to keep event loop free
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, agent_app.invoke, initial_state)
    except Exception as e:
        print(f"[Watcher] Agent failed for task {page_id}: {e}")
        update_notion_task_status(page_id, "FAILED")


async def watch_notion(poll_interval: int = 10):
    """
    Infinite polling loop.
    Fetches pending tasks from Notion and dispatches them to the agent.
    """
    print(f"[Watcher] Starting Notion watcher (poll every {poll_interval}s)...")
    while True:
        try:
            result = read_notion_tasks()
            if result["success"] and result["data"]:
                tasks = result["data"]
                print(f"[Watcher] Found {len(tasks)} pending task(s)")
                for task in tasks:
                    await process_task(task)
            else:
                if not result["success"]:
                    print(f"[Watcher] Error reading Notion: {result['error']}")
        except Exception as e:
            print(f"[Watcher] Unexpected error: {e}")

        await asyncio.sleep(poll_interval)
