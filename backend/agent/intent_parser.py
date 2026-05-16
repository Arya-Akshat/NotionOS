"""
AI Intent Parser — Uses Gemini (primary) or Groq (fallback) to convert
a Notion task description into a structured goal + action plan.

Returns steps as [{tool, args}] for the executor.
"""

import json
import re
import logging
from datetime import datetime
from pydantic import BaseModel, Field

def is_project_scaffolding_task(task_text: str) -> bool:
    """
    Returns True if the task appears to be a project creation request.
    Trigger keywords: launch, build, create, start, set up, scaffold,
    initialize, kickoff, begin, new project, new app, new product,
    new website, new tool, new system, new service
    """
    if not task_text:
        return False
        
    lower = task_text.lower()
    triggers = [
        "launch", "build", "create", "start", "set up", "scaffold",
        "initialize", "kickoff", "begin", "new project", "new app", 
        "new product", "new website", "new tool", "new system", "new service"
    ]
    
    nouns = [
        "app", "site", "product", "tool", "service", "platform", 
        "bot", "system", "mvp", "startup", "business", "portfolio", "saas"
    ]
    
    has_trigger = any(t in lower for t in triggers)
    has_noun = any(n in lower for n in nouns)
    
    return has_trigger and has_noun

def generate_scaffolding_plan(
    task_text: str,
    workspace_style: dict,
    related_pages: list
) -> dict:
    """
    Generates a structured scaffolding plan without calling LLM.
    """
    project_name = _derive_project_name(task_text, workspace_style)
    
    # Apply style to page names
    from tools.workspace_reader import WorkspaceStyleAnalyzer
    style = workspace_style.get("naming_style", {})
    brief_name = WorkspaceStyleAnalyzer.apply_naming_style("Project Brief", style)
    roadmap_name = WorkspaceStyleAnalyzer.apply_naming_style("Roadmap", style)
    db_name = WorkspaceStyleAnalyzer.apply_naming_style("Task Tracker", style)
    
    preview = _generate_workspace_preview(project_name, [brief_name, roadmap_name], db_name, related_pages, style)
    
    return {
        "type": "scaffolding",
        "project_name": project_name,
        "pages_to_create": [brief_name, roadmap_name],
        "database_name": db_name,
        "workspace_style": workspace_style,
        "related_pages": related_pages,
        "workspace_preview": preview,
        "goal": f"Scaffold project workspace for {project_name}"
    }

def _derive_project_name(task_text: str, style_data: dict) -> str:
    """
    Extracts clean project name from task text.
    "Launch my fitness app" -> "Fitness App"
    """
    # Simple regex based extraction
    text = task_text
    
    # Remove trigger words from start
    triggers = ["launch", "build", "create", "start", "set up", "scaffold", "initialize", "kickoff", "begin"]
    for t in triggers:
        text = re.sub(rf"^{t}\s+(my\s+|a\s+|an\s+)?", "", text, flags=re.IGNORECASE)
    
    # Clean up
    text = text.strip().split("\n")[0] # Only first line
    
    # Apply naming style
    from tools.workspace_reader import WorkspaceStyleAnalyzer
    return WorkspaceStyleAnalyzer.apply_naming_style(text, style_data.get("naming_style", {}))

def _generate_workspace_preview(project_name: str,
                              pages: list,
                              db_name: str,
                              related: list,
                              style: dict) -> str:
    """
    Generates the ASCII tree preview string.
    """
    preview = [
        "🏗️ Proposed Workspace Structure",
        f"📁 {project_name}/",
    ]
    for p in pages:
        preview.append(f"├── 📄 {p}")
    
    preview.append(f"├── 🗃️ {db_name}")
    preview.append("│    ├── Properties: Status, Priority, Due Date, Assignee")
    preview.append("│    ├── 📋 Table View")
    preview.append("│    ├── 📌 Kanban Board")
    preview.append("│    └── 📅 Calendar View")
    preview.append("└── 🔖 Execution Log (toggle on parent page)")
    
    if related:
        preview.append("")
        preview.append("Related pages detected:")
        for r in related[:3]:
             preview.append(f"→ [{r.get('title', 'Untitled')}] will be linked in Project Brief")
             
    preview.append("")
    preview.append(f"Naming style: {style.get('case', 'title')} case" + (", with emojis" if style.get("uses_emojis") else ""))
    
    if not preview:
        return "🏗️ Project Scaffolding Pending..."
        
    return "\n".join(preview)
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
import groq
from config import config
from notion_mcp.context import WorkspaceContextBuilder
import asyncio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported tools — ONLY include tools that are fully implemented and executable.
# The planner list is intentionally restricted to prevent invalid actions.
# ---------------------------------------------------------------------------

TOOL_DESCRIPTIONS = {
    "create_repo": "Creates a new GitHub repository. Use for 'create repo', 'initialize github'. args: {name, description}",
    "create_issue": "Creates a GitHub issue. Use for 'open issue', 'report bug'. args: {owner, repo, title, body}",
    "github_open_pr": "Creates a PR with a new file. Use for 'open PR', 'submit code'. args: {owner, repo, title, body, branch_name, file_path, file_content}",
    "github_pr_review_summary": "Reviews a PR and posts a summary. args: {owner, repo, pull_number}",
    "web_search": "Searches the web for info/research. args: {query}",
    "fill_forms": "Automates browser form submission. args: {url, form_data}",
    "search_jobs": "Extracts job listings. args: {query}",
    "update_notion_status": "Updates current task status. args: {status}"
}

IMPLEMENTED_TOOLS = set(TOOL_DESCRIPTIONS.keys())


class ActionStep(BaseModel):
    tool: str = Field(description="Tool name to execute.")
    args: dict = Field(default_factory=dict, description="Keyword arguments for the tool.")


class IntentResponse(BaseModel):
    goal: str = Field(description="A short, clear description of the task's goal.")
    actions: list[ActionStep] = Field(description="Ordered list of tool steps to execute.")


def _get_llm_candidates():
    """
    Returns available fallback LLMs.
    Note: Groq native is handled directly in parse_intent as primary.
    """
    candidates = []

    if config.GEMINI_API_KEY:
        candidates.append((
            "Gemini",
            ChatGoogleGenerativeAI(
                model="gemini-2.0-flash", 
                google_api_key=config.GEMINI_API_KEY,
                temperature=0,
            ),
        ))

    if config.GROQ_API_KEY:
        # Keep ChatGroq as an additional fallback if needed
        candidates.append((
            "Groq_LangChain",
            ChatGroq(
                model="llama-3.3-70b-versatile", 
                api_key=config.GROQ_API_KEY,
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
        r"(?:in|for)\s+(?:repo|repository)\s+([a-zA-Z0-9_.-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()

    slash_ref = re.search(r"\b([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)\b", text)
    if slash_ref:
        return slash_ref.group(2).strip()
    return ""


def _extract_owner(text: str) -> str:
    m = re.search(r"owner\s+([a-zA-Z0-9-]+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    slash_ref = re.search(r"\b([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)\b", text)
    if slash_ref:
        return slash_ref.group(1).strip()
    return ""


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


def _extract_pr_title(text: str) -> str:
    title = _extract_between_quotes(text, r"pr\s+titled?|pull request\s+titled?")
    if not title:
        title = _extract_between_quotes(text, r"titled?")
    return title or "Automated PR"


def _extract_pr_number(text: str) -> int:
    match = re.search(r"(?:pr|pull request)\s*#?(\d+)", text, flags=re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return 0
    return 0


def _extract_branch_name(text: str) -> str:
    match = re.search(r"branch(?:\s+name|\s+named)?\s+([A-Za-z0-9._\-/]+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _heuristic_plan(task_text: str) -> dict:
    """Deterministic fallback planner when LLM providers are unavailable."""
    lower = task_text.lower()
    actions = []

    has_repo = bool(re.search(r"\bcreate\b[^.\n]{0,80}\b(repo|repository)\b", lower)) \
        and not bool(re.search(r"\b(open|create)\s+(?:a\s+)?(?:pull\s+request|pr)\b", lower))
    has_issue = "issue" in lower and any(w in lower for w in ["create", "open"])
    has_search = any(w in lower for w in ["search", "find", "look up", "research"])
    has_open_pr = any(w in lower for w in ["open pr", "create pr", "pull request", "open pull request"]) and "review" not in lower
    has_pr_review = any(w in lower for w in ["pr review", "review pr", "review pull request", "pr summary", "review summary"])

    repo_name = _extract_repo_name(task_text) or "new-project"
    repo_desc = _extract_between_quotes(task_text, r"description")
    owner = _extract_owner(task_text)
    issue_specs = _extract_issue_specs(task_text)
    pr_title = _extract_pr_title(task_text)
    pr_number = _extract_pr_number(task_text)
    branch_name = _extract_branch_name(task_text)

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

    if has_open_pr:
        actions.append({
            "tool": "github_open_pr",
            "args": {
                "owner": owner,
                "repo": repo_name,
                "title": pr_title,
                "body": _extract_between_quotes(task_text, r"pr\s+body|pull request\s+body") or "Automated pull request generated by NotionOS.",
                "base_branch": "main",
                "branch_name": branch_name,
                "file_path": "docs/agent-generated-change.md",
                "file_content": "Automated PR generated from Notion workflow task.",
                "commit_message": "chore: add agent-generated update",
            },
        })

    if has_pr_review:
        actions.append({
            "tool": "github_pr_review_summary",
            "args": {
                "owner": owner,
                "repo": repo_name,
                "pull_number": pr_number,
                "post_comment": True,
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
        "open pr", "create pr", "pull request", "pr review", "review pr",
        "search", "find", "research", "look up",
        "fill form", "submit form",
        "update notion status", "agentstatus",
    ]
    return any(t in lower for t in triggers)


# Build tool description block dynamically — ONLY implemented tools for the planner
_TOOL_LINES = "\n".join([f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()])

PROMPT = PromptTemplate.from_template(
    "You are an expert AI task planner for NotionOS.\n"
    "\n"
    "Your job is to analyze a user's task and return a structured\n"
    "JSON execution plan using the available tools.\n"
    "\n"
    "AVAILABLE TOOLS:\n"
    "- web_search: Search the web for information\n"
    "  args: {{\"query\": \"search query string\"}}\n"
    "\n"
    "- create_repo: Create a GitHub repository\n"
    "  args: {{\"name\": \"repo-name\", \"description\": \"desc\", \"private\": false}}\n"
    "\n"
    "- create_issue: Create an issue in a GitHub repository\n"
    "  args: {{\"repo\": \"repo-name\", \"title\": \"issue title\", \"body\": \"issue body text\"}}\n"
    "\n"
    "- github_open_pr: Open a pull request in a GitHub repository\n"
    "  args: {{\"repo\": \"repo-name\", \"title\": \"PR title\", \"body\": \"PR body text\", \"branch\": \"feature-branch\"}}\n"
    "\n"
    "- github_pr_review_summary: Review and summarize a pull request\n"
    "  args: {{\"repo\": \"repo-name\", \"pr_number\": 1}}\n"
    "\n"
    "- update_notion_status: Update the task status in Notion\n"
    "  args: {{\"status\": \"COMPLETED\"}}\n"
    "\n"
    "- fill_forms: Automate browser interactions and form filling\n"
    "  args: {{\"url\": \"https://...\", \"fields\": {{}} }}\n"
    "\n"
    "RULES:\n"
    "1. Read the ENTIRE task description carefully before planning.\n"
    "2. Extract EVERY action the user wants performed.\n"
    "3. Map each distinct action to the most appropriate tool.\n"
    "4. Preserve all specific details: repo names, issue titles, PR bodies, search queries — extract them exactly as stated.\n"
    "5. Order actions logically (search first, then create, then PR).\n"
    "6. Return ONLY valid JSON. No explanation. No markdown.\n"
    "7. If the user mentions creating a repo then opening an issue or PR on it, use the same repo name across all steps.\n"
    "8. Never omit an action that was explicitly requested.\n"
    "\n"
    "OUTPUT FORMAT (strict JSON only):\n"
    "{{\n"
    "  \"goal\": \"one sentence summary of what this task achieves\",\n"
    "  \"actions\": [\n"
    "    {{\"tool\": \"tool_name\", \"args\": {{...}} }},\n"
    "    {{\"tool\": \"tool_name\", \"args\": {{...}} }}\n"
    "  ]\n"
    "}}\n"
    "\n"
    "Analyze this task and create a complete execution plan.\n"
    "Extract ALL actions mentioned and map each to a tool.\n"
    "\n"
    "TASK:\n"
    "{task}\n"
    "\n"
    "Return a JSON plan covering every action in the task.\n"
    "Use exact names, titles, and descriptions as stated."
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


async def parse_intent(task_title: str, task_text: str) -> dict:
    """
    Parses a natural language intent into a structured plan using LLMs.
    """
    MAX_CONTEXT_TOKENS = 2000

    # 1. Fetch workspace context
    workspace_context = await WorkspaceContextBuilder.build(task_title, task_text)

    
    from graph.workspace_graph import get_workspace_graph
    graph = get_workspace_graph()
    workspace_context["graph_nodes"] = graph.get("nodes", [])[:5]

    # 2. Build context string and enforce token limits (approximation)
    # Simple approx: 1 token ~= 4 chars
    context_str = (
        f"--- WORKSPACE CONTEXT ---\n"
        f"Related Pages: {workspace_context.get('related_pages', [])}\n"
        f"Prior Runs: {workspace_context.get('prior_runs', [])}\n"
        f"Linked Tasks: {workspace_context.get('linked_tasks', [])}\n"
        f"Project Notes: {workspace_context.get('project_notes', [])}\n"
        f"-------------------------\n"
    )

    if len(context_str) > (MAX_CONTEXT_TOKENS * 4):
        trimmed_len = (MAX_CONTEXT_TOKENS * 4)
        diff_tokens = (len(context_str) - trimmed_len) // 4
        context_str = context_str[:trimmed_len] + "\n[TRUNCATED]\n-------------------------\n"
        logger.warning({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "phase": "phase-3",
            "component": "intent_parser",
            "level": "WARNING",
            "event": "context_truncated",
            "detail": f"Context exceeded limit. Trimmed ~{diff_tokens} tokens"
        })

    # Integrate context into task_text for the prompt
    task_text_with_context = f"{context_str}\nTask:\n{task_text}"

    try:
        print(f"[Planner] Analyzing task: {task_text}")

        # 3. Try PRIMARY: Groq Native SDK
        if config.GROQ_API_KEY:
            try:
                print("[Planner] Trying Groq Native (Primary)")
                client = groq.Groq(api_key=config.GROQ_API_KEY)
                prompt_text = PROMPT.format(task=task_text_with_context)
                
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                        {"role": "user", "content": prompt_text}
                    ],
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                parsed = json.loads(content)
                actions = _normalize_actions(parsed.get("actions", []))
                return {
                    "success": True,
                    "provider": "Groq_Native",
                    "data": {
                        "goal": parsed.get("goal", "Unknown goal"),
                        "actions": actions,
                    },
                    "error": None,
                }
            except Exception as e:
                print(f"[Planner] Groq Native failed: {e}")

        # 4. Try FALLBACKS: Gemini, LangChain Groq, etc.
        candidates = _get_llm_candidates()

        for provider_name, llm in candidates:
            print(f"[Planner] Trying {provider_name} LLM (Fallback)")

            # Try structured output first
            try:
                structured_llm = llm.with_structured_output(IntentResponse)
                chain = PROMPT | structured_llm
                response: IntentResponse = chain.invoke({"task": task_text_with_context})
                print(f"[Planner] {provider_name} structured response: {response}")
                actions = _normalize_actions(response.actions)
                return {
                    "success": True,
                    "provider": provider_name,
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
                response = chain.invoke({"task": task_text_with_context})
                content = response.content.strip().strip("```json").strip("```").strip()
                parsed = json.loads(content)
                actions = _normalize_actions(parsed.get("actions", []))
                return {
                    "success": True,
                    "provider": provider_name,
                    "data": {
                        "goal": parsed.get("goal", "Unknown goal"),
                        "actions": actions,
                    },
                    "error": None,
                }
            except Exception as e:
                print(f"[Planner] {provider_name} raw parse failed: {e}")

        print("[Planner] All LLM providers failed, using heuristic fallback planner")
        res = _heuristic_plan(task_text)
        res["provider"] = "Heuristic"
        return res

    except Exception as e:
        print(f"[Planner] Critical error: {e}")
        try:
            return _heuristic_plan(task_text)
        except Exception:
            return {"success": False, "data": {}, "error": f"Intent parsing failed: {str(e)}"}
