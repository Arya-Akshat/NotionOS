"""
Agent Executor – dispatches tool calls based on the execution plan.
Supports step objects {tool, args}. No fake-success placeholders.
Includes retry logic and structured error handling.
"""

import time
from typing import Any
from backend.agent.planner import AgentState
from backend.tools import notion_tool, github_tool, browser_tool
from backend.agent.intent_parser import IMPLEMENTED_TOOLS

# ---------------------------------------------------------------------------
# Notion-safe status values (never emit "Done" or other invalid values)
# ---------------------------------------------------------------------------
VALID_NOTION_STATUSES = {"Pending", "In Progress", "COMPLETED", "FAILED"}

# ---------------------------------------------------------------------------
# Tool registry – ONLY real implementations, no fake-success lambdas
# ---------------------------------------------------------------------------

TOOL_MAP: dict[str, Any] = {
    "search_jobs":          lambda **kw: browser_tool.search_and_extract(kw.get("query", "backend internship jobs")),
    "create_repo":          lambda **kw: github_tool.create_repo(name=kw.get("name", "new-project"), description=kw.get("description", "")),
    "create_issue":         lambda **kw: github_tool.create_issue(owner=kw.get("owner", ""), repo=kw.get("repo", ""), title=kw.get("title", ""), body=kw.get("body", "")),
    "fill_forms":           lambda **kw: browser_tool.fill_form_and_submit(url=kw.get("url", ""), form_data=kw.get("form_data", {}), submit_selector=kw.get("submit_selector", "")),
    "web_search":           lambda **kw: browser_tool.search_and_extract(kw.get("query", "")),
    "update_notion_status": lambda **kw: notion_tool.update_notion_task_status(page_id=kw.get("page_id", ""), new_status=kw.get("status", "In Progress")),
}

MAX_RETRIES = 2
RETRY_DELAY = 1  # seconds


def _normalize_step(step) -> dict:
    """Convert a plan step to {tool, args} format. Handles both strings and dicts."""
    if isinstance(step, str):
        return {"tool": step, "args": {}}
    if isinstance(step, dict):
        return {"tool": step.get("tool", ""), "args": step.get("args", {})}
    return {"tool": str(step), "args": {}}


def _run_tool_with_retry(tool_name: str, args: dict, max_retries: int = MAX_RETRIES) -> dict:
    """Execute a tool function with automatic retry on failure."""
    tool_func = TOOL_MAP.get(tool_name)
    if not tool_func:
        # Not implemented — return honest failure, never fake success
        return {
            "success": False,
            "data": {},
            "error": f"NOT_IMPLEMENTED:{tool_name}",
        }

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            result = tool_func(**args)
            if isinstance(result, dict) and "success" in result:
                if result["success"]:
                    return result
                last_error = result.get("error", "Unknown tool error")
            else:
                return {"success": True, "data": result, "error": None}
        except Exception as e:
            last_error = str(e)

        if attempt < max_retries:
            print(f"[Executor] Retry {attempt}/{max_retries} for '{tool_name}': {last_error}")
            time.sleep(RETRY_DELAY)

    return {
        "success": False,
        "data": {},
        "error": f"Tool '{tool_name}' failed after {max_retries} attempts: {last_error}",
    }


# ---------------------------------------------------------------------------
# Main execute function (called by the graph node)
# ---------------------------------------------------------------------------

def execute_tools(state: AgentState) -> AgentState:
    """Execute the current step in the plan. Respects FAILED status — never
    overwrite FAILED to COMPLETED."""
    # Guard: if already FAILED, don't execute further
    if state.get("status") == "FAILED":
        return state

    plan = state.get("execution_plan", [])
    current_step = state.get("current_step", 0)
    outputs = state.get("tool_outputs", {})

    if current_step >= len(plan):
        state["status"] = "COMPLETED"
        return state

    step = _normalize_step(plan[current_step])
    tool_name = step["tool"]
    args = step["args"]

    print(f"[Executor] Step {current_step + 1}/{len(plan)} → {tool_name}")

    t0 = time.time()
    result = _run_tool_with_retry(tool_name, args)
    duration_ms = int((time.time() - t0) * 1000)
    result["duration_ms"] = duration_ms

    # Store under tool_name (append step index if duplicate)
    key = tool_name if tool_name not in outputs else f"{tool_name}_{current_step}"
    outputs[key] = result

    state["tool_outputs"] = outputs

    if not result["success"]:
        state["errors"] = state.get("errors", []) + [f"{tool_name}: {result['error']}"]
        print(f"[Executor] ⚠ Tool '{tool_name}' failed, continuing pipeline.")

    state["current_step"] = current_step + 1
    if state["current_step"] >= len(plan):
        # Only mark COMPLETED if not already FAILED
        if state.get("status") != "FAILED":
            state["status"] = "COMPLETED"

    return state
