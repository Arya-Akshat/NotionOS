NotionOS — Smart Project Scaffolding
PROMPT.md — Multi-Phase Implementation Guide

HOW TO USE THIS FILE:
Give your IDE this instruction:
"Read PROMPT.md and execute Phase 1. Do not proceed to Phase 2
until all validation checks in Phase 1 pass. Stop generating entirely after 
reporting Phase 1 results and wait for my explicit confirmation."

============================================================
CONTEXT
============================================================
You are adding a new feature called Smart Project Scaffolding
to the existing NotionOS project.
The project already has:

FastAPI backend (backend/main.py)
Notion MCP client (backend/notion_mcp/client.py)
Multi-agent pipeline (ContextAgent, PlannerAgent, ExecutorAgent, ReporterAgent)
Human-in-the-loop approval flow
LangGraph orchestration (backend/workflows/task_agent.py)
Notion watcher (backend/workers/notion_watcher.py)

DO NOT rewrite any existing system.
DO NOT break any existing functionality.
Only ADD the scaffolding feature on top of what exists.

============================================================

GLOBAL SAFETY + UX RULES
============================================================

These rules apply to ALL phases.

RULE 1 — NEVER CREATE ORPHAN NOTION OBJECTS
Every created page/database MUST have:
- a valid parent_id
- a captured returned ID
- a logged creation entry

If parent creation fails:
- abort immediately
- do NOT create any child pages
- mark workflow FAILED

If any child creation fails:
- continue workflow safely
- append ❌ failure entry to execution log
- never leave uncategorized orphan pages in workspace root

============================================================

RULE 2 — IDEMPOTENCY + DUPLICATE EXECUTION SAFETY

The workflow may NOT create duplicate workspaces if:
- watcher runs twice
- approval event fires twice
- websocket reconnect occurs
- backend restarts mid-run

Before creating a workspace:
1. Check whether a parent page already exists for:
   workflow_id OR project_name
2. If found:
   - log WARNING
   - skip duplicate creation
   - reuse existing parent_page_id if safe
3. ExecutorAgent must acquire execution lock before scaffolding.

Recommended implementation:
- in-memory lock OR DB-backed workflow lock
- release lock on completion/failure

============================================================

RULE 3 — ALL MCP CALLS MUST BE WRAPPED

Every MCP operation MUST:
- use timeout handling
- use try/except
- log failures explicitly
- never crash the orchestration engine

Required timeout:
asyncio.wait_for(..., timeout=20)

On timeout:
- append warning to execution_log
- continue gracefully when possible

============================================================

RULE 4 — GENERATED CONTENT QUALITY

Generated workspace content must feel:
- concise
- intentional
- realistic
- human-readable

Avoid:
- generic AI filler
- repetitive wording
- vague bullet spam
- excessive markdown noise

Project Brief content should sound like:
a real early-stage startup/project document.

Roadmap phases should:
- have realistic sequencing
- match project type
- avoid placeholder wording

Task examples must be context-aware.

BAD:
- Build backend
- Create frontend

GOOD:
- Design workout logging experience
- Implement nutrition tracking API
- Create onboarding for fitness goals

============================================================

RULE 5 — LIVE EXECUTION EXPERIENCE

The scaffolding flow should FEEL alive.

After every successful step:
- write execution update immediately
- stream websocket update immediately
- append timestamped execution log immediately

Target user experience:
The user should visibly see the workspace forming in real time.

============================================================

RULE 6 — NOTION-FIRST UX

Prefer writing updates directly into Notion whenever possible.

The dashboard is supplemental.

The PRIMARY user experience should happen inside Notion:
- preview
- approval
- execution progress
- final links
- execution logs

Avoid requiring users to leave Notion unless necessary.

============================================================

RULE 7 — CLEAN NOTION HIERARCHY

Final sidebar structure should remain clean.

Preferred structure:
📁 Parent Project
├── 📄 Project Brief
├── 📄 Roadmap
└── 🗃️ Task Tracker

DO NOT create unnecessary pages.

Execution logs belong INSIDE parent page as toggle blocks,
not as standalone pages.

============================================================

RULE 8 — CROSS-LINK VALIDATION

After workspace creation:
validate all internal links.

Ensure:
- Project Brief links to Roadmap
- Roadmap links to Task Tracker
- Task Tracker references parent project
- Related Work links resolve correctly

Broken Notion links are considered validation failures.

============================================================

RULE 9 — FRONTEND RESILIENCE

Dashboard must gracefully handle:
- websocket reconnects
- delayed workflow updates
- approval latency
- partial execution state

Never assume updates arrive in order.

Frontend should reconcile state using workflow_id and timestamps.

============================================================

RULE 10 — DEMO STABILITY OVER FEATURE COMPLEXITY

If any feature becomes unstable during implementation:
- prefer fallback behavior
- prefer partial success
- prefer simpler UX

DO NOT sacrifice demo reliability for feature sophistication.

A stable, polished workflow is more important than
maximum feature depth.

============================================================

RULE 11 — PRESERVE NON-SCAFFOLDING TASKS

Existing workflows MUST remain unaffected.

Examples:
- web search
- GitHub automation
- Gmail actions
- scheduling workflows

Scaffolding behavior should ONLY activate when:
is_project_scaffolding_task(task_text) == True

All other workflows must follow the existing execution path.

============================================================

RULE 12 — FINAL USER EXPERIENCE TARGET

The final experience should feel like:

"One sentence inside Notion turns into a fully structured,
context-aware project workspace that already feels integrated
with the user's existing knowledge and workflow."

The output should NOT feel like:
- a template dump
- generic AI generation
- disconnected pages

It should feel:
- native to the workspace
- collaborative
- contextual
- intentional
- alive

============================================================
============================================================
FEATURE OVERVIEW
============================================================
When a user creates a task in Notion with a project-intent
title (e.g. "Launch my fitness app", "Build a portfolio site",
"Start a SaaS product"), the agent should:

1. Read the user's existing workspace via notion-search to
understand naming style, prior pages, and related content.
2. Generate a proposed workspace structure that:
- Matches the naming style of the user's existing pages
- References related existing pages
- Links prior work where relevant
3. Show the user a beautiful workspace preview BEFORE approval:

Workspace to be created:
📁 Fitness App/
├── 📄 Project Brief
├── 📄 Roadmap
├── 🗃️ Task Tracker (database)
└── 🔖 Execution Log (callout on parent page)

4. After approval, build the full workspace using Notion MCP:
- Parent page created FIRST, ID captured immediately
- All children use that parent_id — no orphan pages
- Pages reference and link each other internally
- Database uses Notion's standard property names
- Views attempted via MCP, with fallback if unstable
- Execution Log as a callout block on parent page (not a
separate page) to keep sidebar clean
- Write final summary back to original task page.

============================================================
WORKSPACE NAMING CONSISTENCY RULES
============================================================
Before generating any page titles or content, the agent MUST:

1. Use notion-search to fetch 10-15 existing page titles from
the workspace.
2. Analyze the naming style:
- Does user use Title Case or Sentence case?
- Do they use emojis in titles?
- Do they prefer short names or descriptive names?
- Do they use dashes, slashes, or colons as separators?
3. Match that style exactly in all generated titles.

Examples:
User has: "Fitness Research", "Workout Tracker", "Diet Log"
→ Generate: "Fitness App", "Project Brief", "Task Tracker"
(Title Case, no emojis, short names — matches user style)

User has: "🏋️ my workout plan", "📚 reading list 2024"
→ Generate: "🚀 fitness app launch", "📄 project brief"
(lowercase, emojis — matches user style)

If no existing pages found, default to clean Title Case
without emojis.

============================================================
CROSS-REFERENCING RULES
============================================================
Pages must reference each other. Specifically:

- Project Brief must mention: "See Roadmap for timeline"
with a link to the Roadmap page (using Notion page mention)
- Roadmap must mention: "Tasks tracked in Task Tracker"
with a link to the Task Tracker database
- Task Tracker description must mention: "Part of [Project Name]"
with a link back to the parent page

If workspace search found related prior pages, each generated
page must include a "Related Work" section at the bottom
linking to those prior pages.

Example:
User has "Fitness Research" page →
Project Brief gets: "## Related Work\n- [[Fitness Research]]"

============================================================
DATABASE PROPERTY STANDARD
============================================================
When creating the Task Tracker database, always use these
exact property names and types to match Notion's native
Projects & Tasks standard so Notion's Home tab picks them up:

Name        → title (default, always present)
Status      → status (options: "Not started", "In progress", "Done")
Priority    → select (options: "High", "Medium", "Low")
Due Date    → date
Assignee    → people
Project     → relation (to parent page if possible)

**CRITICAL FALLBACK:** If creating a `relation` property via MCP fails 
(which happens if the parent page is not fully indexed yet), gracefully 
catch the error and automatically fallback to creating `Project` as a 
standard `rich_text` property. Do NOT let the database creation crash.

Do NOT invent custom property names. These match Notion's
own internal standards.

============================================================
VIEW CREATION STRATEGY
============================================================
After creating the database, attempt views in this order:

ATTEMPT 1 — via notion-create-view MCP tool:
- Create Kanban board view grouped by Status
- Create Calendar view grouped by Due Date
If both succeed → proceed normally.

ATTEMPT 2 — if notion-create-view fails or times out:
- Do NOT crash the workflow
- Log: "View creation via MCP unavailable, adding guidance"
- Append a callout block to the parent page:
"💡 Tip: Open Task Tracker → Add View → Board (group by
Status) for kanban, or Calendar (group by Due Date) for
timeline view."

Never let view creation failure stop the rest of the workflow.
Always catch exceptions from view creation separately.

============================================================
EXECUTION LOG PLACEMENT
============================================================
The Execution Log must NOT be a separate page in the sidebar.
Instead, append it as a Toggle block at the BOTTOM of the
parent page:

▶ 🤖 Agent Execution Log
├── ✅ Created parent page "Fitness App" (12:47:01)
├── ✅ Created "Project Brief" (12:47:03)
├── ✅ Created "Roadmap" (12:47:05)
├── ✅ Created "Task Tracker" database (12:47:07)
├── ⚠️ Kanban view: created via fallback guidance (12:47:09)
└── ✅ Scaffolding complete (12:47:10)

This keeps the sidebar clean: one project = one sidebar entry.

============================================================
ATOMIC PARENT ID RULE & RATE LIMITING
============================================================
This is a critical technical guardrail.
The scaffolding execution MUST follow this strict order, and MUST
include `await asyncio.sleep(0.5)` between major Notion API calls 
to prevent HTTP 429 Rate Limit errors.

STEP 1: Create parent page → capture parent_page_id immediately
If this fails → abort entire workflow, mark FAILED
STEP 2: Use parent_page_id as parent for ALL subsequent calls:
- Project Brief parent = parent_page_id
- Roadmap parent = parent_page_id
- Task Tracker parent = parent_page_id
Never proceed to step 2 without a confirmed parent_page_id.
STEP 3: Capture IDs of Brief and Roadmap pages after creation.
Use these IDs to create cross-reference links between pages.
STEP 4: Create database with parent = parent_page_id.
Capture database_id immediately after creation.
STEP 5: Create views using database_id.
Wrap in try/except — failure here does NOT abort workflow.
STEP 6: Append execution log toggle to parent page.
STEP 7: Update original task page with summary and links.

============================================================
WORKSPACE PREVIEW FORMAT
============================================================
Before writing proposed actions to Notion for approval, the
agent must generate a workspace preview block that looks like:

🏗️ Proposed Workspace Structure
📁 [Project Name]/
├── 📄 Project Brief
│    └── Problem, Goals, Features, Related Work
├── 📄 Roadmap
│    └── Phase 1: MVP → Phase 2: Beta → Phase 3: Launch
├── 🗃️ Task Tracker
│    ├── Properties: Status, Priority, Due Date, Assignee
│    ├── 📋 Table View
│    ├── 📌 Kanban Board (grouped by Status)
│    └── 📅 Calendar View (grouped by Due Date)
└── 🔖 Execution Log (toggle block on parent page)

Related existing pages detected:
→ [Fitness Research] will be linked in Project Brief
→ [Workout Tracker] will be linked in Roadmap

Naming style detected: Title Case, no emojis (matching your workspace)

This preview is written as a block to the original Notion task page
BEFORE the approval prompt, so the user sees exactly what will
be built before approving.

============================================================
PHASE 1 — WORKSPACE READER
============================================================
Goal: Read and analyze the user's existing Notion workspace
to extract naming style and find related pages.

Files to create:
backend/tools/workspace_reader.py

Files to modify:
backend/agents/context_agent.py

TASK 1.1 — Create backend/tools/workspace_reader.py
Implement class WorkspaceStyleAnalyzer with these methods:

async def analyze_workspace_style(task_title: str) -> dict:
"""
Uses notion-search via mcp_client to read existing pages.
Returns:
{
"naming_style": {
"case": "title" | "sentence" | "lower",
"uses_emojis": bool,
"avg_word_count": int,
"uses_separators": bool,
"separator": "-" | "/" | ":" | None
},
"related_pages": [
{"id": "...", "title": "...", "url": "..."}
],
"prior_similar_projects": [
{"id": "...", "title": "...", "url": "..."}
],
"sample_titles": ["...", "...", "..."]
}
"""

async def detect_naming_style(titles: list[str]) -> dict:
"""
Analyzes a list of page titles and returns naming conventions.
Checks: case style, emoji usage, length, separator chars.
"""

async def find_related_pages(task_title: str,
all_titles: list[dict]) -> list:
"""
Finds pages whose titles share keywords with the task title.
Simple keyword overlap — no LLM needed for this step.
"""

def apply_naming_style(name: str, style: dict) -> str:
"""
Takes a default name like "Project Brief" and converts it
to match the detected style.
Examples:
style case=lower, emojis=True → "📄 project brief"
style case=title, emojis=False → "Project Brief"
"""

Error handling:
If mcp_client.search returns empty or fails:
- Return default style: title case, no emojis
- Return empty related_pages list
- Log WARNING — do not crash

TASK 1.2 — Update backend/agents/context_agent.py
Add workspace style analysis to the ContextAgent.run() method.
After fetching workspace_context, also call:

style_data = await WorkspaceStyleAnalyzer.analyze_workspace_style(
state["task_text"]
)
state["workspace_style"] = style_data

Pass state["workspace_style"] through to PlannerAgent via state dict.

PHASE 1 VALIDATION CHECKS
Run these checks. ALL must pass before proceeding to Phase 2.

CHECK 1.1 — Import test:
cd backend && ./venv/bin/python -c "
from tools.workspace_reader import WorkspaceStyleAnalyzer
print('WorkspaceStyleAnalyzer import: OK')
"

CHECK 1.2 — Style analyzer runs without crash:
cd backend && ./venv/bin/python -c "
import asyncio
from tools.workspace_reader import WorkspaceStyleAnalyzer
async def test():
    result = await WorkspaceStyleAnalyzer.analyze_workspace_style('Launch fitness app')
    print('keys:', list(result.keys()))
    assert 'naming_style' in result
    assert 'related_pages' in result
    assert 'case' in result['naming_style']
    print('Style analyzer: OK')
asyncio.run(test())
"

CHECK 1.3 — apply_naming_style works correctly:
cd backend && ./venv/bin/python -c "
from tools.workspace_reader import WorkspaceStyleAnalyzer
wa = WorkspaceStyleAnalyzer()
s1 = {'case': 'lower', 'uses_emojis': False}
s2 = {'case': 'title', 'uses_emojis': False}
s3 = {'case': 'lower', 'uses_emojis': True, 'emoji': '📄'}
print(wa.apply_naming_style('project brief', s1))
print(wa.apply_naming_style('project brief', s2))
print('apply_naming_style: OK')
"

CHECK 1.4 — ContextAgent passes workspace_style in state:
cd backend && ./venv/bin/python -c "
import asyncio
from agents.context_agent import ContextAgent
state = {'task_id': 'test', 'task_text': 'Launch fitness app', 'workflow_id': 'test-001'}
async def test():
    result = await ContextAgent().run(state)
    assert 'workspace_style' in result, 'workspace_style missing from state'
    print('workspace_style in state: OK')
    print('style:', result['workspace_style']['naming_style'])
asyncio.run(test())
"

REPORT FORMAT:
CHECK 1.1: PASS/FAIL
CHECK 1.2: PASS/FAIL
CHECK 1.3: PASS/FAIL
CHECK 1.4: PASS/FAIL

ALL 4 must be PASS. Fix any failures before asking to proceed.
State: "Phase 1 complete. All checks passed. Awaiting confirmation for Phase 2."
***CRITICAL DIRECTIVE: YOU MUST NOW STOP GENERATING. DO NOT OUTPUT CODE OR TEXT FOR PHASE 2 YET. WAIT FOR THE USER.***

============================================================
PHASE 2 — SCAFFOLDING TOOL
============================================================
Goal: Build the core scaffolding tool that creates the full
Notion workspace structure using MCP tools in strict order.

Files to create:
backend/tools/scaffolding_tool.py

TASK 2.1 — Create backend/tools/scaffolding_tool.py
Implement class ProjectScaffolder with this main method:

async def build_workspace(
project_name: str,
task_page_id: str,
workspace_style: dict,
related_pages: list,
prior_runs: list
) -> dict:
"""
Builds the full project workspace in strict atomic order.
Remember to include `await asyncio.sleep(0.5)` between steps.
Returns:
{
"success": bool,
"parent_page_id": str,
"brief_page_id": str,
"roadmap_page_id": str,
"database_id": str,
"pages_created": list,
"errors": list,
"execution_log": list
}
"""

Implement these internal methods in this exact execution order:

async def _create_parent_page(project_name, style) -> str:
"""
STEP 1. Creates the parent/folder page.
Uses notion-create-pages via mcp_client.
Returns parent_page_id immediately.
If this fails, raises ScaffoldingError — entire workflow aborts.
Icon: use 📁 if user style uses emojis, else no icon.
"""

async def _create_project_brief(parent_page_id, project_name,
style, related_pages) -> str:
"""
STEP 2. Creates Project Brief as child of parent_page_id.
Content sections:
## Problem Statement
[2-3 sentences about the project goal]
## Goals & Success Metrics
- [goal 1]
- [goal 2]
## Target Users
[description]
## Key Features
- [feature 1]
- [feature 2]
## Related Work
[links to related_pages if any found]
---
See [[Roadmap]] for timeline →

Returns brief_page_id.
"""

async def _create_roadmap(parent_page_id, project_name,
brief_page_id, style,
related_pages) -> str:
"""
STEP 3. Creates Roadmap as child of parent_page_id.
Content sections:
## Phase 1: MVP
Goal: [core functionality]
Timeline: Weeks 1-4
## Phase 2: Beta
Goal: [testing + feedback]
Timeline: Weeks 5-8
## Phase 3: Launch
Goal: [public release]
Timeline: Weeks 9-12
---
← [[Project Brief]] | Tasks tracked in [[Task Tracker]] →

Returns roadmap_page_id.
"""

async def _create_task_database(parent_page_id,
project_name,
style,
brief_page_id,
roadmap_page_id) -> str:
"""
STEP 4. Creates Task Tracker database as child of parent_page_id.
Properties MUST match Notion's standard exactly:
- Name (title, default)
- Status (status): "Not started", "In progress", "Done"
- Priority (select): "High", "Medium", "Low"
- Due Date (date)
- Assignee (people)
- Project (relation OR rich_text fallback)
Database description: "Part of [[project_name]] · [[Project Brief]] · [[Roadmap]]"
Returns database_id.
"""

async def _create_views(database_id) -> dict:
"""
STEP 5. Creates views on the database.
Wrapped in try/except — failure does NOT abort workflow.
Attempt 1: notion-create-view Kanban grouped by Status
Attempt 2: notion-create-view Calendar grouped by Due Date
Returns:
{
"kanban_created": bool,
"calendar_created": bool,
"fallback_message": str | None
}
If views fail, fallback_message contains the guidance callout text.
"""

async def _append_execution_log(parent_page_id,
log_entries: list) -> None:
"""
STEP 6. Appends a toggle block to the parent page containing
the execution log. Format:
▶ 🤖 Agent Execution Log
├── ✅ Created parent page (timestamp)
├── ✅ Created Project Brief (timestamp)
...
Uses notion-update-page via mcp_client.
"""

async def _add_view_fallback_callout(parent_page_id,
message: str) -> None:
"""
Only called if _create_views returns fallback_message.
Appends a 💡 callout block to parent page with manual
view creation instructions.
"""

Error handling rules:
- _create_parent_page failure → raise ScaffoldingError,
mark run as FAILED, do not proceed
- _create_project_brief or _create_roadmap failure →
log error, continue with remaining steps, mark partial success
- _create_task_database failure → log error, continue
- _create_views failure → use fallback callout, continue
- All errors appended to execution_log with ❌ prefix

PHASE 2 VALIDATION CHECKS

CHECK 2.1 — Import test:
cd backend && ./venv/bin/python -c "
from tools.scaffolding_tool import ProjectScaffolder
print('ProjectScaffolder import: OK')
"

CHECK 2.2 — Class instantiates correctly:
cd backend && ./venv/bin/python -c "
from tools.scaffolding_tool import ProjectScaffolder
s = ProjectScaffolder()
methods = ['build_workspace', '_create_parent_page',
'_create_project_brief', '_create_roadmap',
'_create_task_database', '_create_views',
'_append_execution_log']
for m in methods:
    assert hasattr(s, m), f'Missing method: {m}'
print('All methods present: OK')
"

CHECK 2.3 — Database property schema is correct:
cd backend && ./venv/bin/python -c "
from tools.scaffolding_tool import ProjectScaffolder
s = ProjectScaffolder()
schema = s._get_database_schema()
required = ['Status', 'Priority', 'Due Date', 'Assignee']
for prop in required:
    assert prop in schema, f'Missing property: {prop}'
    assert schema['Status']['type'] == 'status'
    assert schema['Priority']['type'] == 'select'
print('Database schema: OK')
"

CHECK 2.4 — Error handling: ScaffoldingError exists:
cd backend && ./venv/bin/python -c "
from tools.scaffolding_tool import ScaffoldingError
try:
    raise ScaffoldingError('test error')
except ScaffoldingError as e:
    print('ScaffoldingError works: OK')
"

REPORT FORMAT:
CHECK 2.1: PASS/FAIL
CHECK 2.2: PASS/FAIL
CHECK 2.3: PASS/FAIL
CHECK 2.4: PASS/FAIL

ALL 4 must be PASS. Fix failures before proceeding.
State: "Phase 2 complete. All checks passed. Awaiting confirmation for Phase 3."
***CRITICAL DIRECTIVE: YOU MUST NOW STOP GENERATING. WAIT FOR THE USER.***

============================================================
PHASE 3 — PLANNER INTEGRATION
============================================================
Goal: Update the PlannerAgent to detect project-intent tasks
and generate a scaffolding plan with workspace preview.

Files to modify:
backend/agent/intent_parser.py
backend/agent/planner.py
backend/agents/planner_agent.py

TASK 3.1 — Add project intent detection
In backend/agent/intent_parser.py, add function:

def is_project_scaffolding_task(task_text: str) -> bool:
"""
Returns True if the task appears to be a project creation request.
Trigger keywords: launch, build, create, start, set up, scaffold,
initialize, kickoff, begin, new project, new app, new product,
new website, new tool, new system, new service
Must contain at least one of these AND a noun (app, site, product,
tool, service, platform, bot, system, MVP, startup, business)
"""

TASK 3.2 — Add scaffolding plan generation
In backend/agent/intent_parser.py, add function:

def generate_scaffolding_plan(
task_text: str,
workspace_style: dict,
related_pages: list
) -> dict:
"""
Generates a structured scaffolding plan without calling LLM.
Uses task_text to derive project name.
Uses workspace_style to name pages correctly.
Uses related_pages to populate cross-references.
Returns:
{
"type": "scaffolding",
"project_name": str,
"pages_to_create": ["Project Brief", "Roadmap"],
"database_name": str,
"related_pages": list,
"workspace_preview": str,  ← the ASCII tree preview
"goal": str
}
"""

def _derive_project_name(task_text: str, style: dict) -> str:
"""
Extracts clean project name from task text.
"Launch my fitness app" → "Fitness App" (title case)
"build a portfolio site" → "Portfolio Site"
"create saas mvp for designers" → "SaaS MVP for Designers"
Applies workspace style naming rules.
"""

def _generate_workspace_preview(project_name: str,
pages: list,
db_name: str,
related: list,
style: dict) -> str:
"""
Generates the ASCII tree preview string.
Format:
🏗️ Proposed Workspace Structure
📁 [project_name]/
├── 📄 [page1]
├── 📄 [page2]
├── 🗃️ [db_name]
│    ├── Properties: Status, Priority, Due Date, Assignee
│    ├── 📋 Table View
│    ├── 📌 Kanban Board
│    └── 📅 Calendar View
└── 🔖 Execution Log (toggle on parent page)

Related pages detected:
→ [page] will be linked in Project Brief
Naming style: [style description]
"""

TASK 3.3 — Update planner.py
In backend/agent/planner.py, update plan_workflow():
Before calling parse_intent, check:

if is_project_scaffolding_task(state["task_text"]):
    plan = generate_scaffolding_plan(
        state["task_text"],
        state.get("workspace_style", {}),
        state.get("workspace_context", {}).get("related_pages", [])
    )
    state["execution_plan"] = [{"type": "scaffolding", "data": plan}]
    state["is_scaffolding"] = True
    state["workspace_preview"] = plan["workspace_preview"]
    state["status"] = "WAITING_FOR_APPROVAL"
    return state
else:
    # existing parse_intent flow unchanged
    ...

TASK 3.4 — Update write_proposed_actions in notion_tool.py
Update write_proposed_actions() to detect scaffolding plans
and write the workspace preview instead of a simple bullet list.

If execution_plan[0]["type"] == "scaffolding":
    Write workspace_preview as a code block to the Notion page
    followed by "Approval Status: Pending"
Else:
    Existing bullet list behavior unchanged

PHASE 3 VALIDATION CHECKS

CHECK 3.1 — Intent detection works:
cd backend && ./venv/bin/python -c "
from agent.intent_parser import is_project_scaffolding_task
assert is_project_scaffolding_task('Launch my fitness app') == True
assert is_project_scaffolding_task('Build a portfolio site') == True
assert is_project_scaffolding_task('Search for AI tools') == False
assert is_project_scaffolding_task('Send email to team') == False
print('Intent detection: OK')
"

CHECK 3.2 — Project name derivation:
cd backend && ./venv/bin/python -c "
from agent.intent_parser import generate_scaffolding_plan
style = {'naming_style': {'case': 'title', 'uses_emojis': False}}
plan = generate_scaffolding_plan('Launch my fitness app', style, [])
assert plan['project_name'] == 'Fitness App', f'Got: {plan["project_name"]}'
assert plan['type'] == 'scaffolding'
assert 'workspace_preview' in plan
assert len(plan['workspace_preview']) > 50
print('Plan generation: OK')
print('Project name:', plan['project_name'])
"

CHECK 3.3 — Workspace preview contains expected sections:
cd backend && ./venv/bin/python -c "
from agent.intent_parser import generate_scaffolding_plan
style = {'naming_style': {'case': 'title', 'uses_emojis': False}}
plan = generate_scaffolding_plan('Build a SaaS product', style, [])
preview = plan['workspace_preview']
assert 'Project Brief' in preview
assert 'Roadmap' in preview
assert 'Task Tracker' in preview or 'database' in preview.lower()
assert 'Execution Log' in preview
print('Preview content: OK')
print(preview)
"

CHECK 3.4 — Planner routes correctly:
cd backend && ./venv/bin/python -c "
import asyncio
from agents.planner_agent import PlannerAgent
state = {
'task_id': 'test',
'task_text': 'Launch my fitness app',
'workflow_id': 'test-001',
'workspace_style': {'naming_style': {'case': 'title',
'uses_emojis': False}},
'workspace_context': {'related_pages': []}
}
async def test():
    result = await PlannerAgent().run(state)
    assert result.get('is_scaffolding') == True
    assert result.get('status') == 'WAITING_FOR_APPROVAL'
    assert len(result.get('execution_plan', [])) > 0
    assert result['execution_plan'][0]['type'] == 'scaffolding'
    print('Planner routing: OK')
    print('Status:', result['status'])
asyncio.run(test())
"

REPORT FORMAT:
CHECK 3.1: PASS/FAIL
CHECK 3.2: PASS/FAIL
CHECK 3.3: PASS/FAIL
CHECK 3.4: PASS/FAIL

ALL 4 must be PASS. Fix failures before proceeding.
State: "Phase 3 complete. All checks passed. Awaiting confirmation for Phase 4."
***CRITICAL DIRECTIVE: YOU MUST NOW STOP GENERATING. WAIT FOR THE USER.***

============================================================
PHASE 4 — EXECUTOR INTEGRATION
============================================================
Goal: Wire scaffolding execution into the ExecutorAgent so
that when a scaffolding plan is approved, ProjectScaffolder
is called instead of the standard tool execution loop.

Files to modify:
backend/agents/executor_agent.py
backend/agents/reporter_agent.py

TASK 4.1 — Update ExecutorAgent
In backend/agents/executor_agent.py, update run() method:

async def run(self, state: dict) -> dict:
    # Check if this is a scaffolding execution
    plan = state.get("execution_plan", [])
    if plan and plan[0].get("type") == "scaffolding":
        return await self._run_scaffolding(state)
    else:
        # existing tool execution loop unchanged
        return await self._run_tools(state)

async def _run_scaffolding(self, state: dict) -> dict:
"""
Calls ProjectScaffolder.build_workspace() with:
- project_name from execution_plan[0]["data"]["project_name"]
- task_page_id from state["task_id"]
- workspace_style from state["workspace_style"]
- related_pages from state["workspace_context"]["related_pages"]
- prior_runs from state["workspace_context"]["prior_runs"]

After each internal step, calls append_execution_update()
to stream progress to the Notion task page and dashboard.

On ScaffoldingError → set state["status"] = "FAILED"
On partial success → set state["status"] = "COMPLETED"
note failures in state["errors"]
On full success → set state["status"] = "COMPLETED"

Stores result in state["scaffolding_result"]
"""

Live progress updates during execution (write to task page):
⏳ Creating workspace parent page...
✅ Parent page created: [project_name]
⏳ Creating Project Brief...
✅ Project Brief created with [N] related links
⏳ Creating Roadmap...
✅ Roadmap created
⏳ Creating Task Tracker database...
✅ Task Tracker created with [N] properties
⏳ Setting up views...
✅ Kanban + Calendar views created
(or ⚠️ Views created via guidance callout)
✅ Workspace scaffolding complete

TASK 4.2 — Update ReporterAgent
In backend/agents/reporter_agent.py, update run() to handle
scaffolding results:

If state.get("is_scaffolding") and state.get("scaffolding_result"):
    result = state["scaffolding_result"]
    Write to original task page:
    ## ✅ Workspace Created
    Your project workspace is ready.
    
    **Pages created:**
    - [[Project Brief]] → [url]
    - [[Roadmap]] → [url]
    - [[Task Tracker]] → [url]
    
    **Parent page:** [[project_name]] → [url]
    
    [N] pages created · [N] links added · [duration]s
Else:
    existing reporter behavior unchanged

PHASE 4 VALIDATION CHECKS

CHECK 4.1 — ExecutorAgent handles scaffolding state:
cd backend && ./venv/bin/python -c "
import asyncio
from agents.executor_agent import ExecutorAgent
state = {
'task_id': 'test-page-id',
'task_text': 'Launch fitness app',
'workflow_id': 'test-001',
'is_scaffolding': True,
'workspace_style': {'naming_style': {'case': 'title', 'uses_emojis': False}},
'workspace_context': {'related_pages': [], 'prior_runs': []},
'execution_plan': [{
'type': 'scaffolding',
'data': {
'project_name': 'Fitness App',
'pages_to_create': ['Project Brief', 'Roadmap'],
'related_pages': []
}
}]
}
async def test():
    result = await ExecutorAgent().run(state)
    print('Executor ran scaffolding path: OK')
    print('Status:', result.get('status'))
    print('Has scaffolding_result:', 'scaffolding_result' in result)
asyncio.run(test())
"
Note: This may SKIP(no key) if NOTION_API_KEY is not set.
That is acceptable — we are testing routing only.

CHECK 4.2 — Non-scaffolding tasks still use existing executor:
cd backend && ./venv/bin/python -c "
import asyncio
from agents.executor_agent import ExecutorAgent
state = {
'task_id': 'test',
'task_text': 'search the web for AI tools',
'workflow_id': 'test-002',
'is_scaffolding': False,
'execution_plan': [{'tool': 'web_search', 'args': {'query': 'AI tools'}}]
}
async def test():
    # Should NOT call _run_scaffolding
    result = await ExecutorAgent().run(state)
    print('Non-scaffolding routing: OK')
asyncio.run(test())
"

CHECK 4.3 — ReporterAgent handles scaffolding result:
cd backend && ./venv/bin/python -c "
import asyncio
from agents.reporter_agent import ReporterAgent
state = {
'task_id': 'test-page-id',
'workflow_id': 'test-001',
'is_scaffolding': True,
'status': 'COMPLETED',
'scaffolding_result': {
'success': True,
'parent_page_id': 'abc123',
'pages_created': ['brief', 'roadmap', 'db'],
'errors': [],
'execution_log': []
}
}
async def test():
    result = await ReporterAgent().run(state)
    print('Reporter scaffolding path: OK')
asyncio.run(test())
"
Note: May SKIP(no key). Testing routing only.

REPORT FORMAT:
CHECK 4.1: PASS/FAIL/SKIP(no key)
CHECK 4.2: PASS/FAIL
CHECK 4.3: PASS/FAIL/SKIP(no key)

PASS or SKIP(no key) both acceptable.
Fix actual FAIL before proceeding.
State: "Phase 4 complete. All checks passed. Awaiting confirmation for Phase 5."
***CRITICAL DIRECTIVE: YOU MUST NOW STOP GENERATING. WAIT FOR THE USER.***

============================================================
PHASE 5 — END TO END VALIDATION
============================================================
Goal: Full live test with real Notion API keys.
This phase requires NOTION_API_KEY and NOTION_DATABASE_ID
to be set in backend/.env.

TASK 5.1 — Backend startup check
cd backend && ./venv/bin/python -m uvicorn main:app --port 8000 &
sleep 8
curl -s http://localhost:8000/health
kill %1
Expected: {"db": "ok", "mcp": "ok"} or {"status": "ok"}

TASK 5.2 — Full pipeline dry run
cd backend && ./venv/bin/python -c "
import asyncio
from agents.context_agent import ContextAgent
from agents.planner_agent import PlannerAgent
state = {
'task_id': 'REPLACE_WITH_REAL_NOTION_PAGE_ID',
'task_text': 'Launch my fitness app',
'workflow_id': 'scaffold-test-001'
}
async def test():
    s1 = await ContextAgent().run(state)
    print('Workspace style:', s1.get('workspace_style', {}).get('naming_style'))
    print('Related pages found:', len(s1.get('workspace_style', {}).get('related_pages', [])))

    s2 = await PlannerAgent().run(s1)
    print('Is scaffolding:', s2.get('is_scaffolding'))
    print('Project name:', s2['execution_plan'][0]['data']['project_name'] if s2.get('is_scaffolding') else 'N/A')
    print('Status:', s2.get('status'))
    print()
    print('--- WORKSPACE PREVIEW ---')
    print(s2.get('workspace_preview', 'No preview generated'))
asyncio.run(test())
"
Replace REPLACE_WITH_REAL_NOTION_PAGE_ID with a real page ID
from your workspace before running.

TASK 5.3 — Verify non-scaffolding tasks still work
cd backend && ./venv/bin/python -c "
import asyncio
from agents.planner_agent import PlannerAgent
state = {
'task_id': 'test',
'task_text': 'Search for the top AI tools in 2025',
'workflow_id': 'normal-test-001',
'workspace_style': {'naming_style': {'case': 'title', 'uses_emojis': False}},
'workspace_context': {'related_pages': []}
}
async def test():
    result = await PlannerAgent().run(state)
    assert result.get('is_scaffolding') != True, 'ERROR: Normal task wrongly detected as scaffolding'
    print('Normal task routing: OK')
    print('Status:', result.get('status'))
asyncio.run(test())
"

PHASE 5 VALIDATION CHECKS
CHECK 5.1 — Backend starts clean:         PASS/FAIL
CHECK 5.2 — Scaffolding pipeline runs:    PASS/FAIL/SKIP(no key)
CHECK 5.3 — Normal tasks unaffected:      PASS/FAIL

TASK 5.4 — Live Notion test (manual)
If NOTION_API_KEY is set, do a full live test:

1. Create a Notion task:
Title: "Launch my fitness app"
AgentStatus: Pending
2. Start backend:
cd backend && ./venv/bin/python -m uvicorn main:app --port 8000
3. Wait 15 seconds for watcher to detect task.
4. Open the Notion task page. Verify:
[ ] Workspace preview ASCII tree is written to the page
[ ] "Approval Status: Pending" appears below preview
[ ] Dashboard shows WAITING_FOR_APPROVAL state
5. Approve via dashboard button.
6. Watch Notion. Verify within 60 seconds:
[ ] New parent page appears in sidebar: "Fitness App"
[ ] "Project Brief" page exists under parent
[ ] "Roadmap" page exists under parent
[ ] "Task Tracker" database exists under parent
[ ] Project Brief contains link to Roadmap
[ ] Roadmap contains link to Task Tracker
[ ] Execution log toggle appears at bottom of parent page
[ ] Original task page shows final summary with links
7. Check database properties:
[ ] Status property exists with "Not started/In progress/Done"
[ ] Priority property exists with "High/Medium/Low"
[ ] Due Date property exists
[ ] Assignee property exists

Record results honestly:
Pages created in correct hierarchy:    YES/NO
Cross-references between pages:        YES/NO
Database properties match standard:    YES/NO
Execution log on parent page:          YES/NO
Final summary on task page:            YES/NO
Views created (or fallback guidance):  YES/NO
No orphan pages in sidebar:            YES/NO

State: "Phase 5 complete. All checks passed. Awaiting confirmation for Phase 6."
***CRITICAL DIRECTIVE: YOU MUST NOW STOP GENERATING. WAIT FOR THE USER.***

============================================================
PHASE 6 — CLEANUP AND SAFETY
============================================================
Goal: Ensure the feature is safe, robust, and doesn't break
anything that existed before.

TASK 6.1 — Regression check
Run the existing test suite:
cd backend && ./venv/bin/python -c "
import asyncio
from agents.context_agent import ContextAgent
from agents.planner_agent import PlannerAgent
from agents.executor_agent import ExecutorAgent
from agents.reporter_agent import ReporterAgent

# Test that a non-scaffolding task flows normally
state = {
'task_id': 'test',
'task_text': 'search the web for AI news today',
'workflow_id': 'regression-001',
'workspace_style': {'naming_style': {'case': 'title', 'uses_emojis': False}},
'workspace_context': {'related_pages': [], 'prior_runs': []}
}
async def test():
    s1 = await ContextAgent().run(state)
    s2 = await PlannerAgent().run(s1)
    assert s2.get('is_scaffolding') != True
    print('Regression check: existing tasks unaffected: OK')
    print('Plan type:', s2['execution_plan'][0].get('tool', s2['execution_plan'][0].get('type', 'unknown')) if s2.get('execution_plan') else 'no plan')
asyncio.run(test())
"

TASK 6.2 — Add required imports check
cd backend && ./venv/bin/python -c "
from tools.workspace_reader import WorkspaceStyleAnalyzer
from tools.scaffolding_tool import ProjectScaffolder, ScaffoldingError
from agent.intent_parser import (is_project_scaffolding_task, generate_scaffolding_plan)
print('All new imports resolve: OK')
"

TASK 6.3 — Frontend build check
cd frontend && npm run build 2>&1 | tail -10
Expected: Build completed successfully.

PHASE 6 VALIDATION CHECKS
CHECK 6.1 — Regression: existing tasks unaffected:  PASS/FAIL
CHECK 6.2 — All new imports resolve:                PASS/FAIL
CHECK 6.3 — Frontend builds clean:                  PASS/FAIL
ALL 3 must be PASS.

FINAL REPORT
After all phases complete, produce this report:

PHASE 1 — Workspace Reader          : PASS/FAIL
PHASE 2 — Scaffolding Tool          : PASS/FAIL
PHASE 3 — Planner Integration       : PASS/FAIL
PHASE 4 — Executor Integration      : PASS/FAIL
PHASE 5 — End to End Validation     : PASS/FAIL/PARTIAL
PHASE 6 — Cleanup and Safety        : PASS/FAIL

NEW FILES CREATED:
- backend/tools/workspace_reader.py
- backend/tools/scaffolding_tool.py

FILES MODIFIED:
- backend/agents/context_agent.py
- backend/agents/planner_agent.py
- backend/agents/executor_agent.py
- backend/agents/reporter_agent.py
- backend/agent/intent_parser.py
- backend/agent/planner.py
- backend/tools/notion_tool.py

KNOWN LIMITATIONS:
[ list anything that used fallback behavior ]

DEMO READINESS: READY / NOT READY

============================================================
GIT COMMIT MESSAGE
============================================================
feat(scaffolding): add smart project scaffolding via Notion MCP

- WorkspaceStyleAnalyzer reads existing pages for naming conventions
- ProjectScaffolder builds full workspace with atomic parent ID locking
- Cross-referencing between Brief, Roadmap, and Task Tracker
- Workspace preview shown to user before approval
- Database uses Notion standard property names for Home tab compatibility
- View creation with MCP fallback to guidance callout
- Execution log as toggle block on parent page (not sidebar page)
- Non-scaffolding tasks completely unaffected
- Implemented API rate limit protections and property type fallbacks

============================================================
END OF PROMPT.md
============================================================