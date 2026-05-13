import logging
from datetime import datetime
from notion_mcp.context import WorkspaceContextBuilder

logger = logging.getLogger(__name__)

class ContextAgent:
    async def run(self, state: dict) -> dict:
        logger.info({"event": "agent_start", "component": "ContextAgent", "trace_id": state.get("workflow_id")})
        # Right now intent_parser fetches context directly. So ContextAgent fetches it and puts it into state.
        task_title = state.get("task_id", "Unnamed Task")
        task_text = state.get("task_text", "")
        context = await WorkspaceContextBuilder.build(task_title, task_text)
        state["workspace_context"] = context
        logger.info({"event": "agent_complete", "component": "ContextAgent", "trace_id": state.get("workflow_id")})
        return state
