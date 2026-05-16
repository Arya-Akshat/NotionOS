# NotionOS: The AI-Native Operating System for Notion

NotionOS transforms Notion from a passive documentation tool into an executable operational layer. Built on the **Model Context Protocol (MCP)** and powered by **LangGraph**, it enables autonomous AI agents to plan, coordinate, and safely execute work across multiple tools while remaining grounded in your workspace context.

---

## 🚀 Vision
*“Use Notion as the human-facing operational layer while AI agents interpret, execute, coordinate, and report work in the background.”*

Instead of context-switching between tools, NotionOS treats Notion as your cockpit. Create a task, mark it as Pending, and watch as the system interprets your intent, proposes a plan for approval, and executes it across GitHub, Gmail, and the web.

---

## 🏗️ Architecture

```mermaid
graph TD
    A[Notion Workspace] <--> B[Background Watcher]
    B --> C[LangGraph Orchestrator]
    C --> D[ContextAgent]
    C --> E[PlannerAgent]
    C --> F[Human-in-the-Loop Approval]
    F --> G[ExecutorAgent]
    G <--> H[Tools & MCP Server]
    G --> J[ProjectScaffolder]
    J --> A
    C --> I[ReporterAgent]
    I --> A
```

### Key Engineering Pillars
1. **Deep MCP Integration**: Uses an MCP-first hybrid architecture. The system natively spawns the official `@notionhq/notion-mcp-server` to interact with your workspace as a set of structured tools.
2. **Project Scaffolding Pipeline**: Automatically builds entire project workspaces including Project Briefs, Phase-based Roadmaps, and Task Tracker databases with pre-configured Kanban and Calendar views.
3. **Human-in-the-Loop (HITL)**: Safety is built-in. Every execution plan must be approved via the Notion page or the live Dashboard before side-effects occur.
4. **Real-Time Observability**: A dedicated Next.js dashboard streams execution logs, tool inputs/outputs, and state transitions via WebSockets with specialized visual highlighting for scaffolding tasks.

---

## ✨ Key Features

### 🏢 Workspace Scaffolding
- **Atomic Creation**: Build parent pages, sub-pages, and databases in a single coordinated workflow.
    - **Project Brief**: Rich, domain-specific content generation.
    - **Roadmap**: Automated phase planning and milestone tracking.
    - **Task Tracker**: Pre-populated database with Status, Priority, and Assignee properties.
- **Premium Notion UI**: Uses Notion callouts, bold highlights, and quote blocks for professional-grade reporting and workspace organization.

### 📊 Real-Time Dashboard
- **WebSocket Streaming**: Live log updates with sub-millisecond latency.
- **Visual Gating**: Interactive approval system for proposed agent plans.
- **Granular Progress**: Real-time construction logs for scaffolding tasks highlighted in **Violet** for high visibility.

---

## 🛠️ Tech Stack
- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS 4.
- **Backend**: FastAPI (Python), SQLAlchemy (SQLite).
- **Agent Orchestration**: LangGraph, LangChain.
- **AI Models**: Groq (Llama 3.3 70b) for speed, Google (Gemini 2.0 Flash) for complex planning.
- **Protocol**: Model Context Protocol (MCP) via stdio transport.

---

## 🏁 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- Notion Internal Integration Token
- Groq or Google Gemini API Key

### 2. Environment Setup
Copy `.env.example` to `.env` and fill in your keys:
```bash
NOTION_API_KEY=your_token
NOTION_DATABASE_ID=your_db_id
GROQ_API_KEY=your_key
GEMINI_API_KEY=your_key
```

### 3. Installation
```bash
# Install backend dependencies
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install frontend dependencies
cd ../frontend
npm install
```

### 4. Running the System
```bash
# Start the Backend (starts the MCP server & Watcher automatically)
cd backend
python main.py

# Start the Frontend
cd ../frontend
npm run dev
```

---

## 🤖 Integrated Tools
- **GitHub**: Repository creation, issue management, and automated Pull Requests.
- **Search**: Tavily-powered web research and extraction.
- **Browser**: Playwright-based form filling and web interaction.
- **Notion**: Status management, block appending, and workspace context retrieval.
- **Scaffolder**: Direct HTTP-based database and page orchestration for high reliability.

---

## 🛡️ Safety & Reliability
- **Duplicate Execution Guards**: Strict workflow locking using state-aware ID tracking.
- **State Persistence**: Every step is logged to a local database for full auditability and resumption.
- **Hybrid Mode**: Automatic fallback to direct REST API calls if the MCP abstraction layer encounters schema mismatches.

---

## 📝 License
MIT
