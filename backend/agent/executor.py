import time
import asyncio
import inspect
from typing import Any
from agent.planner import AgentState
from tools import notion_tool, github_tool, browser_tool
from agent.intent_parser import IMPLEMENTED_TOOLS

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
        "github_open_pr":       lambda **kw: github_tool.github_open_pr(
                                                                owner=kw.get("owner", ""),
                                                                repo=kw.get("repo", ""),
                                                                title=kw.get("title", "Automated PR"),
                                                                body=kw.get("body", ""),
                                                                base_branch=kw.get("base_branch", "main"),
                                                                branch_name=kw.get("branch_name", ""),
                                                                file_path=kw.get("file_path", "docs/agent-generated-change.md"),
                                                                file_content=kw.get("file_content", ""),
                                                                commit_message=kw.get("commit_message", "chore: add agent-generated update"),
                                                            ),
        "github_pr_review_summary": lambda **kw: github_tool.github_pr_review_summary(
                                                                owner=kw.get("owner", ""),
                                                                repo=kw.get("repo", ""),
                                                                pull_number=int(kw.get("pull_number", 0) or 0),
                                                                post_comment=bool(kw.get("post_comment", True)),
                                                            ),
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


async def _run_tool_with_retry(tool_name: str, args: dict, max_retries: int = MAX_RETRIES) -> dict:
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
            # Execute sync or async tool
            if inspect.iscoroutinefunction(tool_func) or asyncio.iscoroutine(tool_func):
                 result = await tool_func(**args)
            else:
                 # Check if the lambda/func returns a coroutine
                 result = tool_func(**args)
                 if asyncio.iscoroutine(result):
                     result = await result
            
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
            await asyncio.sleep(RETRY_DELAY)

    return {
        "success": False,
        "data": {},
        "error": f"Tool '{tool_name}' failed after {max_retries} attempts: {last_error}",
    }


# ---------------------------------------------------------------------------
# Main execute function (called by the graph node)
# ---------------------------------------------------------------------------

async def execute_tools(state: AgentState) -> AgentState:
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

    step_obj = plan[current_step]
    
    # -----------------------------------------------------------------------
    # SCAFFOLDING INTERCEPTION
    # -----------------------------------------------------------------------
    if isinstance(step_obj, dict) and step_obj.get("type") == "scaffolding":
        print("[Executor] 🏗️ Detected Scaffolding Plan — routing to ProjectScaffolder")
        from tools.scaffolding_tool import ProjectScaffolder
        scaffolder = ProjectScaffolder()
        
        data = step_obj.get("data", {})
        project_name = data.get("project_name", "New Project")
        workspace_style = data.get("workspace_style", {})
        related_pages = data.get("related_pages", [])
        
        try:
            res = await scaffolder.build_workspace(
                project_name=project_name,
                task_page_id=state["task_id"],
                workspace_style=workspace_style,
                related_pages=related_pages,
                prior_runs=state.get("workspace_context", {}).get("prior_runs", []),
                workflow_id=str(state.get("workflow_id", ""))
            )
            
            outputs["scaffolding"] = res
            if res.get("success"):
                state["status"] = "COMPLETED"
                state["current_step"] = current_step + 1
            else:
                state["status"] = "FAILED"
                state["errors"] = state.get("errors", []) + res.get("errors", [])
        except Exception as e:
            state["status"] = "FAILED"
            state["errors"] = state.get("errors", []) + [f"Scaffolding orchestration failed: {e}"]
        
        state["tool_outputs"] = outputs
        return state

    # Standard tool execution
    step = _normalize_step(step_obj)
    tool_name = step["tool"]
    args = step["args"]

    print(f"[Executor] Step {current_step+1}/{len(plan)}: {tool_name}")
    
    # Tool duration tracking
    start_time = time.time()
    result = await _run_tool_with_retry(tool_name, args)
    duration_ms = int((time.time() - start_time) * 1000)
    result["duration_ms"] = duration_ms

    # Use tool_name as key, or tool_name_{index} if multiple
    output_key = tool_name
    if tool_name in outputs:
        output_key = f"{tool_name}_{current_step}"
    
    outputs[output_key] = result
    state["tool_outputs"] = outputs

    if result.get("success"):
        state["current_step"] = current_step + 1
        if state["current_step"] >= len(plan):
            if state.get("status") != "FAILED":
                state["status"] = "COMPLETED"
    else:
        state["status"] = "FAILED"
        state["errors"] = state.get("errors", []) + [result.get("error")]

    return state
