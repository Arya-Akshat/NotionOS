"""
AI Intent Parser — Uses Gemini (primary) or Groq (fallback) to convert
a Notion task description into a structured goal + action plan.

Returns steps as [{tool, args}] for the executor.
"""

import json
import re
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from backend.config import config


# ---------------------------------------------------------------------------
# Supported tools — ONLY include tools that are fully implemented and executable.
# The planner list is intentionally restricted to prevent invalid actions.
# ---------------------------------------------------------------------------

IMPLEMENTED_TOOLS = {
    "search_jobs", "create_repo", "create_issue",
    "fill_forms", "web_search", "update_notion_status",
}


class ActionStep(BaseModel):
    tool: str = Field(description="Tool name to execute.")
    args: dict = Field(default_factory=dict, description="Keyword arguments for the tool.")


class IntentResponse(BaseModel):
    goal: str = Field(description="A short, clear description of the task's goal.")
    actions: list[ActionStep] = Field(description="Ordered list of tool steps to execute.")


def _get_llm_candidates():
    """
    Returns available LLMs in priority order.
    We try each candidate and fall back on provider/rate-limit errors.
    """
    candidates = []

    if config.GOOGLE_API_KEY:
        candidates.append((
            "Gemini",
            ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=config.GOOGLE_API_KEY,
                temperature=0,
            ),
        ))

    if config.GROQ_API_KEY:
        candidates.append((
            "Groq",
            ChatOpenAI(
                model="llama-3.3-70b-versatile",
                api_key=config.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
                temperature=0,
            ),
        ))

    return candidates


def _extract_between_quotes(text: str, label: str) -> str:
    pattern = rf"(?:{label})\s*[\"']([^\"']+)[\"']"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    value = m.group(1) if m else ""
    return value.strip() if isinstance(value, str) else ""


def _extract_repo_name(text: str) -> str:
    patterns = [
        r"repo\s+named\s+([a-zA-Z0-9_.-]+)",
        r"repository\s+named\s+([a-zA-Z0-9_.-]+)",
        r"create\s+(?:a\s+)?repo\s+([a-zA-Z0-9_.-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _extract_owner(text: str) -> str:
    m = re.search(r"owner\s+([a-zA-Z0-9-]+)", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_search_query(text: str) -> str:
    cleaned = text.strip()
    split_match = re.split(r"\bthen\s+create\b", cleaned, maxsplit=1, flags=re.IGNORECASE)
    return split_match[0].strip() if split_match else cleaned


def _extract_issue_specs(text: str) -> list[dict]:
    specs = []
    pattern = re.compile(
        r"issue\s+titled\s+[\"']([^\"']+)[\"'](?:\s+with\s+body\s+[\"']([^\"']*)[\"'])?",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        title = (match.group(1) or "").strip()
        body = (match.group(2) or "").strip()
        if title:
            specs.append({"title": title, "body": body})

    return specs


def _heuristic_plan(task_text: str) -> dict:
    """Deterministic fallback planner when LLM providers are unavailable."""
    lower = task_text.lower()
    actions = []

    has_repo = any(w in lower for w in ["create repo", "create repository", "repo named", "repository named"])
    has_issue = "issue" in lower and any(w in lower for w in ["create", "open"])
    has_search = any(w in lower for w in ["search", "find", "look up", "research"])

    repo_name = _extract_repo_name(task_text) or "new-project"
    repo_desc = _extract_between_quotes(task_text, r"description")
    owner = _extract_owner(task_text)
    issue_specs = _extract_issue_specs(task_text)

    if has_search:
        actions.append({
            "tool": "web_search",
            "args": {"query": _extract_search_query(task_text)},
        })

    if has_repo:
        actions.append({
            "tool": "create_repo",
            "args": {
                "name": repo_name,
                "description": repo_desc,
            },
        })

    if has_issue:
        if not issue_specs:
            fallback_title = _extract_between_quotes(task_text, r"titled?|issue titled") or "Initial issue"
            fallback_body = _extract_between_quotes(task_text, r"body")
            issue_specs = [{"title": fallback_title, "body": fallback_body}]

        for issue in issue_specs:
            actions.append({
                "tool": "create_issue",
                "args": {
                    "owner": owner,
                    "repo": repo_name,
                    "title": issue.get("title", "Initial issue"),
                    "body": issue.get("body", ""),
                },
            })

    if not actions:
        actions.append({"tool": "web_search", "args": {"query": task_text}})

    return {
        "success": True,
        "data": {
            "goal": task_text[:120],
            "actions": _normalize_actions(actions),
        },
        "error": None,
    }


def _should_use_heuristic_first(task_text: str) -> bool:
    """Use deterministic planning first for clearly mappable tool intents."""
    lower = task_text.lower()
    triggers = [
        "create repo", "create repository", "repo named", "repository named",
        "create issue", "open issue", "issue titled",
        "search", "find", "research", "look up",
        "fill form", "submit form",
        "update notion status", "agentstatus",
    ]
    return any(t in lower for t in triggers)


# Build tool description block dynamically — ONLY implemented tools for the planner
_TOOL_LINES = "\n".join(f"- {t}" for t in sorted(IMPLEMENTED_TOOLS))

PROMPT = PromptTemplate.from_template(
    "You are an AI assistant orchestrating workflow tasks.\n"
    "Analyze the following task: '{task}'\n\n"
    "Available tools:\n" + _TOOL_LINES + "\n\n"
    "Return a JSON object with:\n"
    '  "goal": "<short description>",\n'
    '  "actions": [\n'
    '    {{"tool": "<tool_name>", "args": {{...}} }},\n'
    "    ...\n"
    "  ]\n"
    "Each action must use a tool from the list above.\n"
    "args should contain relevant parameters as key-value pairs.\n"
    "Output ONLY valid JSON, nothing else."
)


def _normalize_actions(raw_actions: list) -> list[dict]:
    """Normalize actions and validate against implementation list."""
    normalized = []
    for action in raw_actions:
        tool_name = ""
        args = {}
        
        if isinstance(action, str):
            tool_name = action
        elif isinstance(action, dict):
            tool_name = action.get("tool", "")
            args = action.get("args", {})
            if isinstance(args, str):
                args = {}
        elif isinstance(action, ActionStep):
            tool_name = action.tool
            args = action.args
            
        if tool_name not in IMPLEMENTED_TOOLS:
             raise ValueError(f"Planner selected unimplemented tool: '{tool_name}'")
             
        normalized.append({"tool": tool_name, "args": args})
    return normalized


def parse_intent(task_text: str) -> dict:
    """
    Parses a natural language Notion task into a structured goal and action plan.
    Returns { success, data: { goal, actions: [{tool, args}] }, error }.
    """
    try:
        print(f"[Planner] Analyzing task: {task_text}")

        if _should_use_heuristic_first(task_text):
            print("[Planner] Using heuristic-first planner for deterministic task intent")
            return _heuristic_plan(task_text)

        candidates = _get_llm_candidates()

        for provider_name, llm in candidates:
            print(f"[Planner] Trying {provider_name} LLM")

            # Try structured output first
            try:
                structured_llm = llm.with_structured_output(IntentResponse)
                chain = PROMPT | structured_llm
                response: IntentResponse = chain.invoke({"task": task_text})
                print(f"[Planner] {provider_name} structured response: {response}")
                actions = _normalize_actions(response.actions)
                return {
                    "success": True,
                    "data": {"goal": response.goal, "actions": actions},
                    "error": None,
                }
            except Exception as e:
                if isinstance(e, ValueError):
                    print(f"[Planner] Validation Error: {e}")
                    return {"success": False, "data": {}, "error": str(e)}

                print(f"[Planner] {provider_name} structured output failed, trying raw JSON: {e}")

            # Fallback: raw text -> parse JSON manually
            try:
                chain = PROMPT | llm
                response = chain.invoke({"task": task_text})
                print(f"[Planner] {provider_name} raw text response: {response.content}")
                content = response.content.strip().strip("```json").strip("```").strip()
                parsed = json.loads(content)
                actions = _normalize_actions(parsed.get("actions", []))
                return {
                    "success": True,
                    "data": {
                        "goal": parsed.get("goal", "Unknown goal"),
                        "actions": actions,
                    },
                    "error": None,
                }
            except Exception as e:
                print(f"[Planner] {provider_name} raw parse failed: {e}")

        print("[Planner] All LLM providers failed, using heuristic fallback planner")
        return _heuristic_plan(task_text)

    except Exception as e:
        print(f"[Planner] Critical error: {e}")
        try:
            return _heuristic_plan(task_text)
        except Exception:
            return {"success": False, "data": {}, "error": f"Intent parsing failed: {str(e)}"}
