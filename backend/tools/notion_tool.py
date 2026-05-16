import requests
import asyncio
import logging
from datetime import datetime
from typing import Optional
from config import config
from notion_mcp.client import mcp_client

logger = logging.getLogger(__name__)

NOTION_API_KEY = config.NOTION_API_KEY
NOTION_VERSION = "2022-06-28"
NOTION_DATABASE_ID = config.NOTION_DATABASE_ID
DEFAULT_TIMEOUT = 10.0

def _log_mcp(level: str, tool_name: str):
    # Log structured event
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "phase": "phase-2",
        "component": "notion_tool",
        "level": level,
        "event": "mcp_tool_call",
        "detail": tool_name,
        "trace_id": ""
    }
    if level == "WARNING":
        logger.warning(str(log_entry))
        print(log_entry)
    else:
        logger.info(str(log_entry))
        print(log_entry)

def _run_mcp_sync(coro):
    """Run async MCP calls safely in synchronous contexts."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        # Fallback if somehow called inside an active loop (unlikely in worker thread)
        import threading
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    return loop.run_until_complete(coro)

async def _try_mcp(tool_name: str, coro) -> Optional[dict]:
    """Execute MCP tool operations directly. Return None to trigger HTTP fallback on failure."""
    if config.NOTION_MCP_ENABLED and config.NOTION_MCP_MODE in ("hybrid", "mcp"):
        _log_mcp("INFO", tool_name)
        try:
            result = await coro
            # Standardizing MCP success response layout to match tool contract
            return {"success": True, "data": result, "error": None}
        except Exception as e:
            _log_mcp("WARNING", f"{tool_name} failed: {str(e)}")
            return None
    return None

def _normalize_notion_status(status: str) -> str:
    """Map internal workflow status values to Notion select labels."""
    if not isinstance(status, str):
        return "Pending"

    key = status.strip().lower().replace("_", " ")
    mapping = {
        "pending": "Pending",
        "planning": "Planning",
        "executing": "In Progress",
        "in progress": "In Progress",
        "completed": "Completed",
        "failed": "Failed",
    }
    return mapping.get(key, status)

def _get_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

def read_notion_tasks(database_id: str = None):
    """
    Reads pending tasks from the specified Notion Database.
    """
    db_id = database_id or NOTION_DATABASE_ID
    if not db_id:
        return {"success": False, "data": {}, "error": "NOTION_DATABASE_ID_MISSING"}

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    
    payload = {
        "filter": {
            "property": "AgentStatus",
            "select": {
                "equals": "Pending"
            }
        }
    }

    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_API_ERROR:{response.status_code}:{response.text}"}
        
        data = response.json()
        tasks = []
        for page in data.get("results", []):
            try:
                # Notion's default Title column is often named 'Name'
                props = page["properties"]
                name_list = props.get("Name", {}).get("title", []) or props.get("Title", {}).get("title", [])
                title = name_list[0]["text"]["content"] if name_list else "Untitled"
                
                goal_prop = props.get("Goal", {}).get("rich_text", [])
                goal = goal_prop[0]["text"]["content"] if goal_prop else ""
                
                tasks.append({
                    "page_id": page["id"],
                    "title": title,
                    "goal": goal
                })
            except Exception:
                continue
                
        return {"success": True, "data": tasks, "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_UNEXPECTED_ERROR:{str(e)}"}

async def update_notion_task_status(page_id: str, status: str):
    label = _normalize_notion_status(status)
    properties = {
        "AgentStatus": {
            "select": {"name": label}
        }
    }
    
    mcp_res = await _try_mcp(f"update_page ({label})", mcp_client.update_page(page_id, properties))
    if mcp_res is not None: return mcp_res

    # Fallback HTTP
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": properties}

    try:
        response = requests.patch(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_UPDATE_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_UPDATE_ERROR:{str(e)}"}

async def create_notion_page(database_id: str, title: str, content: str = ""):
    """
    Creates a new page/entry in the specified database.
    """
    db_id = database_id or NOTION_DATABASE_ID
    
    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        }
    }
    
    payload = {
        "parent": { "database_id": db_id },
        "properties": properties
    }
    
    arguments_for_mcp = {
        "parent": {"type": "database_id", "database_id": db_id},
        "properties": properties
    }
    
    if content:
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            }
        ]
        payload["children"] = children
        arguments_for_mcp["children"] = children

    # Phase 2: Intercept with MCP
    # Use standard Notion MCP create_page signature approximation
    mcp_res = await _try_mcp("create_page", mcp_client.invoke_tool("create_page", arguments_for_mcp))
    if mcp_res is not None:
        return mcp_res

    url = "https://api.notion.com/v1/pages"
    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_CREATE_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_CREATE_ERROR:{str(e)}"}

async def append_log_to_page(page_id: str, log_text: str):
    """Appends a log entry to the Notion page using direct HTTP."""
    print(f"[Notion] Appending log to {page_id}")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    payload = {
        "children": [
            {
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": log_text}, "annotations": {"italic": True}}]
                }
            }
        ]
    }
    try:
        response = requests.patch(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            logger.error(f"Failed to append log: {response.status_code} {response.text}")
            return {"success": False, "error": f"HTTP_{response.status_code}"}
        return {"success": True}
    except Exception as e:
        logger.error(f"Error appending log: {e}")
        return {"success": False, "error": str(e)}

async def append_result_to_page(page_id: str, lines: list[str]):
    """Appends multiple result lines to the Notion page using direct HTTP."""
    print(f"[Notion] Appending results to {page_id}")
    if not lines:
        return {"success": True}

    children = []
    for line in lines:
        if not line or not isinstance(line, str): continue
        
        # Determine block type
        block_type = "paragraph"
        if line == "📋 Summary of Findings": block_type = "heading_3"
        elif line.startswith("Search Result ") or line.startswith("Repository:") or line.startswith("Issue "):
            block_type = "bulleted_list_item"

        children.append({
            "object": "block",
            "type": block_type,
            block_type: {
                "rich_text": [{"type": "text", "text": {"content": line[:2000]}}] # Notion limit
            }
        })

    # Notion limit is 100 children per request
    for i in range(0, len(children), 100):
        chunk = children[i:i+100]
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        try:
            response = requests.patch(url, headers=_get_headers(), json={"children": chunk}, timeout=DEFAULT_TIMEOUT)
            if response.status_code != 200:
                logger.error(f"Failed to append results: {response.status_code} {response.text}")
                return {"success": False, "error": f"HTTP_{response.status_code}"}
        except Exception as e:
            logger.error(f"Error appending results: {e}")
            return {"success": False, "error": str(e)}
    
    return {"success": True}

async def write_proposed_actions(page_id: str, actions: list, preview: str = ""):
    children = [
        {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "--- Proposed Actions ---"}}]}}
    ]
    
    # If scaffolding, show the preview block
    if actions and actions[0].get("type") == "scaffolding" and preview:
        children.append({
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": preview}}],
                "language": "plain text"
            }
        })
    else:
        for action in actions:
            children.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": str(action.get('tool', 'Tool'))}}]}})
            
    children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "Approval Status: Pending"}}]}})

def get_approval_status(page_id: str) -> str:
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    try:
        r = requests.get(url, headers=_get_headers(), timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            for b in reversed(r.json().get("results", [])):
                if b["type"] == "paragraph":
                    rt = b["paragraph"]["rich_text"]
                    if rt and "Approval Status:" in rt[0]["text"]["content"]:
                        return rt[0]["text"]["content"].replace("Approval Status:", "").strip()
    except: pass
    return "Pending"

async def write_initial_headers(page_id: str):
    """Initializes the task page with clean, professional sections."""
    children = [
        {"object": "block", "type": "divider", "divider": {}},
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📍 Project Status & Results"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "Below is the summary of the agent's work and the final output."}, "annotations": {"italic": True}}]}},
        {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🔄 Execution Timeline"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "Tracking tool calls and progress in real-time..."}}]}}
    ]
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    try:
        requests.patch(url, headers=_get_headers(), json={"children": children}, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        logger.warning(f"Failed to write initial headers: {e}")

async def append_execution_update(page_id: str, step_name: str, status: str, detail: str = ""):
    """Appends a status update using bullet points for a cleaner look."""
    icon = "⏳" if status == "running" else "✅" if status == "complete" else "❌"
    text = f"{step_name}: {status}"
    if detail:
        text += f" ({detail})"
    
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    payload = {
        "children": [
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{icon} "}},
                        {"type": "text", "text": {"content": text}, "annotations": {"bold": (status == "running")}}
                    ]
                }
            }
        ]
    }
    try:
        requests.patch(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        logger.error(f"Error appending execution update: {e}")

async def write_run_separator(page_id: str):
    """Adds a visual separator for a new run with a clean timestamp."""
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    children = [
        {"object": "block", "type": "divider", "divider": {}},
        {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": f"🚀 NotionOS Run"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"Initiated on {timestamp}"}, "annotations": {"italic": True, "color": "gray"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "Approval Status: Pending"}, "annotations": {"bold": True, "color": "orange"}}]}},
        {"object": "block", "type": "divider", "divider": {}},
    ]
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    try:
        requests.patch(url, headers=_get_headers(), json={"children": children}, timeout=DEFAULT_TIMEOUT)
    except: pass

async def write_scaffolding_result(page_id: str, project_name: str, project_url: str):
    """Writes a prominent success message with a big link to the new project."""
    children = [
        {"object": "block", "type": "divider", "divider": {}},
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "✨ Success! Your workspace is ready.\n\n"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"The project '{project_name}' has been scaffolded with all requested components."}}
                ],
                "icon": {"type": "emoji", "emoji": "🏗️"},
                "color": "green_background"
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": "👉 Open Project: "}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": project_name}, "link": {"url": project_url}, "annotations": {"bold": True, "color": "blue"}}
                ]
            }
        },
        {"object": "block", "type": "divider", "divider": {}}
    ]
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    try:
        requests.patch(url, headers=_get_headers(), json={"children": children}, timeout=DEFAULT_TIMEOUT)
    except: pass
