"""
MCP Context utilities.
"""
from typing import Dict, Any
from .client import mcp_client
from config import config
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class WorkspaceContextBuilder:
    @staticmethod
    async def build(task_title: str, task_content: str) -> Dict[str, Any]:
        """
        Build structured context by combining workspace state via MCP.
        Falls back to empty context silently on error.
        """
        context = {
            "related_pages": [],
            "linked_tasks": [],
            "prior_runs": [],
            "project_notes": [],
            "metadata": {"task_title": task_title}
        }
        
        if not config.NOTION_MCP_ENABLED or config.NOTION_MCP_MODE not in ("hybrid", "mcp"):
            return context
            
        try:
            # 1. Fetch linked tasks from the primary database
            tasks_res = await mcp_client.query_database(config.NOTION_DATABASE_ID)
            if tasks_res:
                # Basic normalization of results
                context["linked_tasks"] = tasks_res[:5]
                context["metadata"]["source"] = "mcp"

            # 2. Search for related pages by title
            search_res = await mcp_client.search_pages(task_title)
            if search_res:
                context["related_pages"] = search_res[:5]
                context["metadata"]["source"] = "mcp"

        except Exception as e:
            logger.warning({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "phase": "phase-3",
                "component": "WorkspaceContextBuilder", 
                "level": "WARNING",
                "event": "mcp_context_fetch_error",
                "detail": str(e)
            })
            context["metadata"]["source"] = "fallback"
            
        return context

