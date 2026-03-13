import requests
from backend.config import config

NOTION_API_KEY = config.NOTION_API_KEY
NOTION_VERSION = "2022-06-28"
NOTION_DATABASE_ID = config.NOTION_DATABASE_ID
DEFAULT_TIMEOUT = 10.0

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

def update_notion_task_status(page_id: str, new_status: str):
    """
    Updates the AgentStatus property of a specific task in Notion.
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    
    payload = {
        "properties": {
            "AgentStatus": {
                "select": {
                    "name": new_status
                }
            }
        }
    }

    try:
        response = requests.patch(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_UPDATE_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_UPDATE_ERROR:{str(e)}"}

def create_notion_page(database_id: str, title: str, content: str = ""):
    """
    Creates a new page/entry in the specified database.
    """
    url = "https://api.notion.com/v1/pages"
    db_id = database_id or NOTION_DATABASE_ID
    
    payload = {
        "parent": { "database_id": db_id },
        "properties": {
            "Name": {
                "title": [{"text": {"content": title}}]
            }
        }
    }
    
    if content:
        payload["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            }
        ]

    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_CREATE_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_CREATE_ERROR:{str(e)}"}

def append_log_to_page(page_id: str, log_text: str):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    payload = {
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": f"🤖 Agent Log: {log_text}"}}]
                }
            }
        ]
    }
    
    try:
        response = requests.patch(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_APPEND_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_APPEND_ERROR:{str(e)}"}


def append_result_to_page(page_id: str, lines: list[str]):
    """Append a compact result section to a Notion page with readable block types."""
    safe_lines = []
    for line in lines:
        if not isinstance(line, str):
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Notion text content has practical size limits; keep paragraphs small.
        chunk_size = 1800
        for start in range(0, len(stripped), chunk_size):
            safe_lines.append(stripped[start:start + chunk_size])

    clean_lines = safe_lines
    if not clean_lines:
        return {"success": True, "data": {}, "error": None}

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"

    def _make_text_block(block_type: str, content: str):
        return {
            "object": "block",
            "type": block_type,
            block_type: {
                "rich_text": [{"type": "text", "text": {"content": content}}]
            }
        }

    children = []
    for line in clean_lines:
        if line == "Agent Result":
            children.append(_make_text_block("heading_3", line))
        elif line.startswith("Search Result ") or line.startswith("Repository:") or line.startswith("Issue "):
            children.append(_make_text_block("bulleted_list_item", line))
        else:
            children.append(_make_text_block("paragraph", line))

    payload = {"children": children}

    try:
        response = requests.patch(url, headers=_get_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            return {"success": False, "data": {}, "error": f"NOTION_APPEND_ERROR:{response.status_code}"}
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.Timeout:
        return {"success": False, "data": {}, "error": "NOTION_TIMEOUT"}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"NOTION_APPEND_ERROR:{str(e)}"}
