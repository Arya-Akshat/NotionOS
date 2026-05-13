"""
NotionOS LangGraph workflow — hardened agent loop.
- Planner failure never reaches executor.
- FAILED status is never overwritten.
- Tool logs include input, output, and duration_ms.
- Broadcast events are emitted for real-time dashboard.
"""

import re
import time
from urllib.parse import urlparse
from langgraph.graph import StateGraph, END
from agent.planner import AgentState, plan_workflow
from agent.executor import execute_tools, _normalize_step
from database import SessionLocal
from models.logs import AgentRun, ToolCallLog
from tools.notion_tool import update_notion_task_status, append_log_to_page, append_result_to_page

# ---------------------------------------------------------------------------
# WebSocket broadcast bridge — imported lazily at call-time to avoid
# circular imports (main.py imports us, we import main's broadcast).
# ---------------------------------------------------------------------------

def _broadcast_event(event_type: str, payload: dict):
    """Fire-and-forget broadcast to connected dashboard clients via thread-safe dispatcher."""
    try:
        from main import dispatch_broadcast
        dispatch_broadcast({"type": event_type, **payload})
    except Exception as e:
        print(f"[WS] Broadcast trigger failed ({event_type}): {e}")


# ---------------------------------------------------------------------------
# Database logging helpers
# ---------------------------------------------------------------------------

async def initialize_agent_run(state: AgentState):
    """Binds to an existing AgentRun or creates a new one (fail-safe)."""
    wf_id = state.get("workflow_id")
    db = SessionLocal()
    try:
        if wf_id:
            # Look up the row created by the watcher
            run = db.query(AgentRun).filter(AgentRun.id == wf_id).first()
            if run:
                # Update status to PENDING if it was PLANNING
                run.status = "PENDING"
                db.commit()
                db.refresh(run)
                state["status"] = "PENDING"
        else:
            # Fail-safe: create if watcher somehow missed it
            run = AgentRun(
                notion_task_id=state.get("task_id", "unknown_id"),
                status="PENDING",
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            state["workflow_id"] = run.id

        _broadcast_event("run_created", {"run_id": run.id, "status": "PENDING"})
    except Exception as e:
        print(f"[DB] Failed to initialize/bind agent run: {e}")
    finally:
        db.close()
    
    state = await sync_agent_run(state)
    return state


async def sync_agent_run(state: AgentState):
    """Persists current agent state to DB and broadcasts status update."""
    wf_id = state.get("workflow_id")
    if not wf_id:
        return state

    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter(AgentRun.id == wf_id).first()
        if run:
            run.status = state.get("status", "UNKNOWN")
            run.goal = state.get("goal", "")
            run.execution_plan = state.get("execution_plan", [])
            run.current_step = state.get("current_step", 0)
            run.tool_outputs = state.get("tool_outputs", {})
            run.errors = state.get("errors", [])
        from tools.notion_tool import write_proposed_actions
        if state.get("status") == "WAITING_FOR_APPROVAL":
            await write_proposed_actions(state.get("task_id"), state.get("execution_plan", []))
            from tools.notion_tool import write_initial_headers
            await write_initial_headers(state.get("task_id"))
            db.commit()
            _broadcast_event("run_status_updated", {
                "run_id": wf_id,
                "status": state.get("status"),
            })
    except Exception as e:
        print(f"[DB] Failed to sync agent run: {e}")
    finally:
        db.close()
    return state


def log_tool_call(agent_run_id: int, tool_name: str, tool_input: dict, result: dict):
    """Writes a single tool-call record with input, output, and duration."""
    db = SessionLocal()
    try:
        entry = ToolCallLog(
            agent_run_id=agent_run_id,
            tool_name=tool_name,
            tool_input=tool_input,
            status="success" if result.get("success") else "failed",
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
            "status": entry.status,
            "duration_ms": result.get("duration_ms"),
        })
    except Exception as e:
        print(f"[DB] Failed to log tool call: {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

async def planner_node(state: AgentState):
    """Runs intent parsing + planning, then syncs status."""
    # SKIP if already approved/executing to prevent re-planning
    if state.get("status") == "EXECUTING":
        return state
        
    state = await plan_workflow(state)
    state = await sync_agent_run(state)
    return state


def entry_router(state: AgentState):
    """Entry router: EXECUTING → execute loop, otherwise → start from initialization."""
    status = state.get("status", "")
    if status == "EXECUTING":
        return "execute_and_log"
    return "initialize_agent_run"


def after_planner(state: AgentState):
    """Router after planner: FAILED → finalize, EXECUTING → execute loop,
    otherwise → fail-safe finalize."""
    status = state.get("status", "")
    if status == "FAILED":
        return "finalize"
    if status == "WAITING_FOR_APPROVAL":
        return "end"
    if status == "EXECUTING":
        return "execute_and_log"
    # Unexpected status — fail-safe finalize
    return "finalize"


async def execute_and_log(state: AgentState):
    """Executes the current tool step and logs the result to DB."""
    # Guard — never execute if already FAILED
    if state.get("status") == "FAILED":
        return state

    current_step = state.get("current_step", 0)
    plan = state.get("execution_plan", [])

    step = _normalize_step(plan[current_step]) if current_step < len(plan) else None
    tool_name = step["tool"] if step else None
    tool_args = step["args"] if step else {}

    state = execute_tools(state)

    # Persist tool result with input + duration
    if tool_name and state.get("workflow_id"):
        outputs = state.get("tool_outputs", {})
        # Find the output — may be stored as tool_name or tool_name_{step}
        result = outputs.get(tool_name) or outputs.get(f"{tool_name}_{current_step}", {})
        log_tool_call(state["workflow_id"], tool_name, tool_args, result)

    state = await sync_agent_run(state)
    return state


def should_continue_executing(state: AgentState):
    """Router: decide next node for the execute loop."""
    status = state.get("status", "")
    if status == "FAILED":
        return "finalize"
    if status == "COMPLETED":
        return "finalize"
    plan = state.get("execution_plan", [])
    if status == "EXECUTING" and state.get("current_step", 0) < len(plan):
        return "execute_and_log"
    return "finalize"


def _format_search_snippet(snippet: str) -> str:
    text = snippet or ""
    text = text.replace("\n", " ")
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"#+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return text


def _format_source_label(link: str) -> str:
    if not link:
        return ""
    parsed = urlparse(link)
    host = parsed.netloc or link
    return host.removeprefix("www.")


def _collect_result_lines(status: str, total: int, succeeded: int, failed: int, errors: list[str], outputs: dict) -> list[str]:
    lines = ["Agent Result", f"Status: {status}"]

    if total > 0:
        lines.append(f"Steps: {succeeded}/{total} succeeded, {failed} failed")

    repo_url = None
    issue_urls = []
    search_result_lines = []

    for result in outputs.values():
        if not isinstance(result, dict) or not result.get("success"):
            continue

        data = result.get("data") or {}
        if not isinstance(data, dict):
            continue

        results = data.get("results")
        if isinstance(results, list) and results:
            query = data.get("query")
            if isinstance(query, str) and query:
                search_result_lines.append(f"Search Query: {query}")
            search_result_lines.append("Search Highlights")

            for index, item in enumerate(results[:3], start=1):
                if not isinstance(item, dict):
                    continue
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")
                clean_title = title.strip() if isinstance(title, str) else ""
                clean_snippet = _format_search_snippet(snippet) if isinstance(snippet, str) else ""
                source_label = _format_source_label(link) if isinstance(link, str) else ""

                text = f"Search Result {index}: {clean_title}" if clean_title else f"Search Result {index}"
                if source_label:
                    text = f"{text} ({source_label})"
                if clean_snippet:
                    text = f"{text} - {clean_snippet}"
                search_result_lines.append(text)

        html_url = data.get("html_url")
        if not isinstance(html_url, str) or not html_url:
            continue

        if "/issues/" in html_url:
            issue_urls.append(html_url)
        else:
            repo_url = html_url

    if repo_url:
        lines.append(f"Repository: {repo_url}")

    for index, issue_url in enumerate(issue_urls[:3], start=1):
        lines.append(f"Issue {index}: {issue_url}")

    lines.extend(search_result_lines)

    if errors:
        lines.append(f"Errors: {'; '.join(errors[:3])}")

    return lines


async def finalize_node(state: AgentState):
    """Final node: updates Notion page with status and concise summary.
    Handles both COMPLETED and FAILED runs."""
    page_id = state.get("task_id", "")
    status = state.get("status", "COMPLETED")

    # Build concise summary
    plan = state.get("execution_plan", [])
    outputs = state.get("tool_outputs", {})
    errors = state.get("errors", [])

    succeeded = sum(1 for v in outputs.values() if isinstance(v, dict) and v.get("success"))
    failed = sum(1 for v in outputs.values() if isinstance(v, dict) and not v.get("success"))
    total = len(plan)

    summary_lines = [f"Status: {status}"]
    if total > 0:
        summary_lines.append(f"Steps: {succeeded}/{total} succeeded, {failed} failed")
    if errors:
        summary_lines.append(f"Errors: {'; '.join(errors[:3])}")

    summary = " | ".join(summary_lines)

    if page_id:
        await update_notion_task_status(page_id, status)
        await append_log_to_page(page_id, summary)
        await append_result_to_page(page_id, _collect_result_lines(status, total, succeeded, failed, errors, outputs))

    state = await sync_agent_run(state)
    return state


# ---------------------------------------------------------------------------
# Build the LangGraph workflow
# ---------------------------------------------------------------------------

workflow = StateGraph(AgentState)

workflow.add_node("initialize_agent_run", initialize_agent_run)
workflow.add_node("planner_node", planner_node)
workflow.add_node("execute_and_log", execute_and_log)
workflow.add_node("finalize", finalize_node)

workflow.set_conditional_entry_point(entry_router)
workflow.add_edge("initialize_agent_run", "planner_node")

# After planner: FAILED → finalize, EXECUTING → execute loop
workflow.add_conditional_edges("planner_node", after_planner)

# Execute loop: continue or finalize
workflow.add_conditional_edges("execute_and_log", should_continue_executing)

workflow.add_edge("finalize", END)

# Compiled graph
agent_app = workflow.compile()

def approve_workflow(run_id: int):
    db = SessionLocal()
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if run:
        run.status = "EXECUTING"
        db.commit()
    db.close()

async def reject_workflow(run_id: int):
    """Marks the workflow as FAILED due to user rejection."""
    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run:
            run.status = "FAILED"
            run.errors = (run.errors or []) + ["User rejected the execution plan."]
            db.commit()
            
            # Update Notion to reflect the rejection
            if run.notion_task_id:
                await update_notion_task_status(run.notion_task_id, "FAILED")
    except Exception as e:
        print(f"[DB] Rejection sync failed: {e}")
    finally:
        db.close()
