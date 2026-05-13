import logging
from datetime import datetime
from tools.notion_tool import update_notion_task_status, append_result_to_page, append_execution_update, _try_mcp, mcp_client, _get_headers
import requests
from config import config

logger = logging.getLogger(__name__)

class ReporterAgent:
    async def run(self, state: dict) -> dict:
        logger.info({"event": "agent_start", "component": "ReporterAgent", "trace_id": state.get("workflow_id")})
        page_id = state.get("task_id", "")
        status = state.get("status", "COMPLETED")

        plan = state.get("execution_plan", [])
        outputs = state.get("tool_outputs", {})
        total = len(plan)

        # Write Final Summary
        summary_text = f"Goal: {state.get('goal', '')} | Status: {status} | Steps: {total} | Duration: N/A"
        
        children = [
            {"object": "block", "type": "divider", "divider": {}},
            {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "--- Final Summary ---"}}]}},
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": summary_text}}]}}
        ]
        
        if page_id:
            try:
                update_notion_task_status(page_id, status)
                # mcp append
                mcp_res = _try_mcp("append_block_children (final)", mcp_client.append_blocks(page_id, children))
                if mcp_res is None:
                    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
                    requests.patch(url, headers=_get_headers(), json={"children": children}, timeout=10)
            except Exception as e:
                logger.warning(f"[ReporterAgent] failed to update Notion: {e}")
                
        logger.info({"event": "agent_complete", "component": "ReporterAgent", "trace_id": state.get("workflow_id")})
        return state
