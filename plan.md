# NotionOS — Complete Project Context, Architecture Report, and Upgrade Roadmap

## Current Status

NotionOS is an AI-agent orchestration platform built around the idea of turning Notion into an executable operational workspace rather than a passive note-taking application.

The project was built for the Notion MCP Challenge and successfully won the challenge. As part of the win, there is now an opportunity to meet Ivan Zhao, CEO and Co-Founder of Notion. Because of this, the project is now entering a second phase of development focused on transforming it from a strong technical prototype into a deeply Notion-native AI operating system aligned with the long-term philosophy of Notion and MCP.

The current goal is no longer simply to demonstrate automation. The goal is now to evolve NotionOS into a system that feels like the future of AI-powered work orchestration inside Notion itself.

This document contains:

* complete project context
* current architecture
* workflow explanation
* file inventory
* tech stack
* implemented systems
* strengths and weaknesses
* migration path toward proper Notion MCP usage
* future upgrade roadmap

This report is intended to provide complete context to external AI systems, collaborators, reviewers, and engineering assistants.

---

# Core Vision

The central idea behind NotionOS is:

“Use Notion as the human-facing operational layer while AI agents interpret, execute, coordinate, and report work in the background.”

The system treats Notion as:

* task input surface
* workflow trigger system
* operational dashboard
* persistent memory layer
* execution reporting interface

Instead of building a separate operations panel or command system, users work entirely from inside Notion.

A user creates a task inside a Notion database, marks it as Pending, and the system autonomously:

* detects the task
* interprets intent
* generates an execution plan
* invokes tools
* logs execution
* streams updates
* writes results back into Notion

The long-term vision is to evolve this into:
“An AI-native operating system built on top of Notion.”

---

# Current Architecture Overview

The project currently consists of two major systems:

1. Backend orchestration engine
2. Frontend operational dashboard

The backend is responsible for:

* task polling
* workflow orchestration
* AI planning
* tool execution
* state management
* database logging
* WebSocket broadcasting

The frontend is responsible for:

* displaying runs
* displaying logs
* visualizing workflow progress
* showing live execution updates

---

# High-Level Workflow

## Current Workflow

1. User creates task inside Notion database
2. User sets AgentStatus = Pending
3. Background watcher polls Notion every 10 seconds
4. Pending task is detected
5. Task marked In Progress
6. Initial workflow state created
7. LangGraph planner interprets task
8. Planner generates structured execution plan
9. Executor processes steps sequentially
10. Tools are invoked
11. Tool results are logged
12. WebSocket events emitted
13. Frontend dashboard updates live
14. Final summary written back into Notion
15. Task marked Completed or Failed

---

# Current Technical Stack

## Frontend

* Next.js 16
* React 19
* TypeScript
* Tailwind CSS 4

## Backend

* FastAPI
* Uvicorn
* SQLAlchemy
* PostgreSQL
* SQLite (local dev artifact)

## AI / Agent Framework

* LangGraph
* LangChain

## LLM Routing

* Gemini (primary)
* Groq (fallback)
* Ollama planned for local fallback

## External Integrations

* Notion API
* GitHub API
* Gmail API
* Google Calendar API
* Tavily Search
* Playwright browser automation

## Realtime Infrastructure

* WebSockets

## Validation / Config

* Pydantic
* python-dotenv

---

# Current Core Concept

The current system behaves like:

Task in Notion
→ AI planning
→ tool orchestration
→ execution
→ reporting back to Notion

The project already supports:

* autonomous workflows
* multi-tool execution
* persistent execution state
* real-time observability
* structured agent planning

---

# Current Strengths

## 1. Strong Systems Architecture

The project is not just an LLM wrapper.

It contains:

* orchestration layer
* workflow state machine
* execution pipeline
* logging infrastructure
* frontend observability
* retry handling
* persistent execution state

This makes it significantly more advanced than many typical AI demos.

---

## 2. Cross-Tool Automation

The system already integrates:

* GitHub
* Notion
* Gmail
* Google Calendar
* Playwright

This allows the agent to coordinate work across multiple systems.

---

## 3. Real Agent Workflow

The system supports:

* task interpretation
* structured planning
* execution sequencing
* retry logic
* workflow completion states

The workflow is significantly more agentic than most challenge submissions.

---

## 4. Real-Time Observability

The dashboard streams:

* execution logs
* workflow states
* tool events
* run progress

This makes the system feel alive and operational.

---

# Current Weaknesses

Although technically strong, the project currently has several weaknesses relative to Notion’s long-term vision.

## 1. Notion Is Still Mostly a Trigger Layer

Currently:

* Notion acts mainly as:

  * input surface
  * status tracker
  * reporting destination

The actual orchestration intelligence lives mostly outside Notion.

This creates the perception of:
“AI system with Notion integration”
rather than:
“Notion-native AI operating system”

---

## 2. The Project Does NOT Yet Properly Use Notion MCP

This is the most important architectural limitation.

Current system:

* primarily uses direct Notion API integration
* backend directly performs reads/writes

This is NOT equivalent to proper MCP-native architecture.

Currently:
Agent
→ Backend
→ Notion API

Target architecture:
Agent
→ MCP Client
→ Notion MCP Server
→ Notion Workspace

The migration toward true MCP integration is now a major priority.

---

## 3. Lack of Human-in-the-Loop Execution

Current workflows are highly autonomous.

While impressive technically, this is less aligned with:

* safe AI systems
* collaborative AI
* Notion’s product philosophy

The project needs:

* approval flows
* collaborative execution
* AI suggestions
* user confirmation systems

---

## 4. Limited Workspace Context Usage

The current planner mostly interprets:

* task text

It does NOT yet deeply understand:

* related pages
* databases
* prior workflows
* workspace graph
* project memory
* linked context

This prevents Notion from functioning as a true memory layer.

---

# Existing Repository Structure

## Root

* README.md
* .env.example
* plan.md
* demo.mp4
* images/
* backend/
* frontend/

---

# Backend Structure

## backend/main.py

Primary FastAPI entry point.

Responsibilities:

* app startup
* DB initialization
* launching watcher
* REST APIs
* WebSocket endpoint

---

## backend/workers/notion_watcher.py

Background polling worker.

Responsibilities:

* polling Notion
* detecting pending tasks
* initializing workflow state
* invoking LangGraph workflow

---

## backend/workflows/task_agent.py

Core LangGraph workflow definition.

Responsibilities:

* initializing runs
* synchronizing state
* logging execution
* executing plan
* finalizing workflows
* updating Notion

---

## backend/agent/intent_parser.py

LLM planning layer.

Responsibilities:

* converting task text into:

  * normalized goal
  * execution plan
  * action list
* validating supported tools

---

## backend/agent/executor.py

Execution engine.

Responsibilities:

* running tool steps
* retries
* capturing outputs
* updating workflow state

---

# Existing Tool Layer

## notion_tool.py

Capabilities:

* fetch tasks
* update status
* append logs
* create pages

---

## github_tool.py

Capabilities:

* create repositories
* create issues
* PR workflows
* review summaries

---

## gmail_tool.py

Capabilities:

* send email
* read inbox

---

## calendar_tool.py

Capabilities:

* create events
* list events

---

## browser_tool.py

Capabilities:

* Tavily search
* browser automation
* page interaction
* form submission

---

# Existing Database Layer

## logs.py

Stores:

* runs
* execution plans
* tool logs
* timestamps
* errors
* durations

This gives the system strong observability.

---

# Existing Frontend

## Dashboard.tsx

Displays:

* active runs
* workflow logs
* run details
* live updates

Uses:

* REST APIs
* WebSockets

---

# Current Runtime Workflow Example

Example task:

“Launch AI SaaS MVP”

Current execution:

1. watcher detects task
2. planner generates:

   * create_repo
   * generate_tasks
   * schedule_sessions
3. GitHub repo created
4. Notion subtasks generated
5. Calendar events created
6. Logs streamed to dashboard
7. Final summary written back into Notion

---

# Why The Project Won

The project won because of:

* strong systems thinking
* multi-tool orchestration
* agent workflow architecture
* execution observability
* real automation
* operational UX
* ambitious AI systems design

It stood out as:
“An AI operating layer for work orchestration.”

---

# Comparison Against Other Winning Projects

Compared to projects like NoteRunway:

* NoteRunway was more polished and deeply Notion-native
* NotionOS was more ambitious and architecturally advanced

NotionOS currently excels in:

* orchestration
* multi-tool execution
* agent coordination
* operational infrastructure

But it still needs:

* stronger MCP usage
* deeper Notion-native interaction
* collaborative workflows
* richer contextual understanding

---

# Current Strategic Goal

The project is now entering a second major phase.

The new objective is:

Transform NotionOS from:
“AI orchestration platform with Notion integration”

into:
“A true Notion-native AI operating system built on MCP.”

---

# Immediate Migration Priority — Proper MCP Integration

## Current Problem

Current integration uses:

* direct Notion API calls

This is insufficient for a fully MCP-native architecture.

---

# Target MCP Architecture

Desired flow:

User
→ Notion Workspace
→ MCP Server
→ MCP Client
→ Agent System
→ Tool Execution
→ Result Sync

---

# Planned MCP Migration

## Step 1 — Add Official Notion MCP Server

Planned integration:
@notionhq/notion-mcp-server

Purpose:

* expose Notion as AI-native tools/resources
* allow structured agent interaction
* move away from direct backend orchestration

---

## Step 2 — Replace Direct Writes With MCP Tool Calls

Currently:
backend directly patches pages

Target:
agent invokes MCP tools instead

Examples:

* create page
* update page
* archive page
* append content

through MCP interface.

---

## Step 3 — Introduce MCP Client Layer

Create:
backend/mcp/

Responsibilities:

* MCP client connection
* stdio communication
* tool routing
* context fetching

---

## Step 4 — Convert Notion Into Context Engine

Current:
task text only

Target:
agent reads:

* related pages
* linked databases
* project history
* workspace graph
* prior workflows

before planning.

This makes Notion the true memory layer.

---

# Planned Major Upgrades

## Upgrade 1 — Human-in-the-Loop Workflows

Add:

* approval requests
* suggested plans
* execution confirmation

Inside Notion itself.

Example:

Agent proposes:

* create GitHub repo
* generate roadmap
* schedule sessions

User approves before execution.

---

## Upgrade 2 — Interactive Notion Agent

Inside Notion:

* AI suggestions
* execution summaries
* collaborative planning
* status updates

Goal:
make the experience feel native to Notion.

---

## Upgrade 3 — Workspace Memory System

Agent remembers:

* previous workflows
* project context
* user behavior
* preferred schedules
* historical tasks

This creates adaptive planning.

---

## Upgrade 4 — Workspace Graph Understanding

Agent understands:

* database relations
* linked pages
* dependencies
* project hierarchy

This is one of the largest planned conceptual upgrades.

---

## Upgrade 5 — Multi-Agent Collaboration

Potential future agents:

* planner agent
* execution agent
* research agent
* reporting agent

All coordinated through Notion.

---

## Upgrade 6 — Better Real-Time UX

Current:
polling-heavy architecture

Planned:

* richer event-driven UX
* streaming updates
* native progress feedback

---

# Long-Term Vision

Long-term, NotionOS aims to become:

“A collaborative AI operating system built around human context, structured knowledge, and executable workflows.”

The final desired experience is:

* users work naturally inside Notion
* agents understand workspace context
* workflows are collaboratively executed
* AI safely proposes and performs actions
* execution remains observable and inspectable
* Notion becomes both the interface and the memory layer

---

# Final Positioning

The strongest positioning for the project is:

“NotionOS transforms Notion into an executable AI-native operating system where agents can plan, coordinate, and safely execute work across tools while remaining grounded in human context.”

---

# Current Development Direction

The immediate development roadmap is:

1. migrate to true MCP architecture
2. deepen Notion-native interaction
3. add human approval workflows
4. add workspace memory/context reasoning
5. improve collaborative execution
6. evolve from orchestration engine into AI workspace operating system

This document should be treated as the canonical project context for future development discussions, architectural planning, AI-assisted coding, and strategic refinement.
