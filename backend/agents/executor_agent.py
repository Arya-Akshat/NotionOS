
import time
import logging

logger = logging.getLogger(__name__)

def execute_with_retry(func, *args, **kwargs):
    retries = 3
    delays = [1, 2, 4]
    
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if '429' in str(e): # Notion rate limit
                time.sleep(60)
                return func(*args, **kwargs)
                
            if attempt < retries - 1:
                logger.warning(f"Tool failed, retrying in {delays[attempt]}s... Error: {e}")
                time.sleep(delays[attempt])
            else:
                logger.error(f"Tool failed after {retries} attempts: {e}")
                return f"Failed: {e}"
                
    return "Failed"
import logging
from datetime import datetime
from agent.executor import execute_tools
from tools.notion_tool import append_execution_update

logger = logging.getLogger(__name__)

class ExecutorAgent:
    async def run(self, state: dict) -> dict:
        logger.info({"event": "agent_start", "component": "ExecutorAgent", "trace_id": state.get("workflow_id")})
        
        plan = state.get("execution_plan", [])
        current_step_idx = state.get("current_step", 0)
        page_id = state.get("task_id", "")
        
        # DEBUG PRINTS
        print(f"[Executor] is_scaffolding={state.get('is_scaffolding')}")
        if plan and current_step_idx < len(plan):
            step_type = plan[current_step_idx].get("type") if isinstance(plan[current_step_idx], dict) else "unknown"
            print(f"[Executor] plan type={step_type}")
        else:
            print(f"[Executor] plan empty or index out of range")

        # Detect scaffolding
        if current_step_idx < len(plan):
            step = plan[current_step_idx]
            if isinstance(step, dict) and step.get("type") == "scaffolding":
                # Guard against re-execution
                if state.get("scaffolding_complete"):
                    print("[Scaffolding] Already completed, skipping.")
                    return state
                state["scaffolding_complete"] = True
                
                # Scaffolding handles its own execution updates internally
                state = await execute_tools(state)
                # Capture result for Reporter
                if "scaffolding" in state.get("tool_outputs", {}):
                    state["scaffolding_result"] = state["tool_outputs"]["scaffolding"]
                
                logger.info({"event": "agent_complete", "component": "ExecutorAgent", "trace_id": state.get("workflow_id")})
                return state

        # Standard tool execution
        if current_step_idx < len(plan):
            step = plan[current_step_idx]
            tool_name = step.get("tool", "") if isinstance(step, dict) else step
            
            # Write Running update
            if page_id:
                await append_execution_update(page_id, tool_name, "running")
            
            # Execute
            state = await execute_tools(state)
            
            # Find the result
            outputs = state.get("tool_outputs", {})
            key = tool_name if tool_name in outputs else f"{tool_name}_{current_step_idx}"
            res = outputs.get(key, {})
            
            status_val = "complete" if res.get("success") else "failed"
            detail = "" if res.get("success") else res.get("error", "")
            
            if page_id:
                await append_execution_update(page_id, tool_name, status_val, detail)
        else:
            state = await execute_tools(state) # will just mark completed
            
        logger.info({"event": "agent_complete", "component": "ExecutorAgent", "trace_id": state.get("workflow_id")})
        return state
