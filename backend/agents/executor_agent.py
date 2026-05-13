
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
        
        # We need to run execution for the current step and write an update to Notion
        plan = state.get("execution_plan", [])
        current_step_idx = state.get("current_step", 0)
        page_id = state.get("task_id", "")
        
        # Because execute_tools advances current_step, we capture the info before it runs
        if current_step_idx < len(plan):
            step = plan[current_step_idx]
            tool_name = step.get("tool", "") if isinstance(step, dict) else step
            
            # Write Running update
            if page_id:
                append_execution_update(page_id, tool_name, "running")
            
            # Execute
            state = execute_tools(state)
            
            # Find the result
            outputs = state.get("tool_outputs", {})
            key = tool_name if tool_name in outputs else f"{tool_name}_{current_step_idx}"
            res = outputs.get(key, {})
            
            status_val = "complete" if res.get("success") else "failed"
            detail = "" if res.get("success") else res.get("error", "")
            
            if page_id:
                append_execution_update(page_id, tool_name, status_val, detail)
        else:
            state = execute_tools(state) # will just mark completed
            
        logger.info({"event": "agent_complete", "component": "ExecutorAgent", "trace_id": state.get("workflow_id")})
        return state
