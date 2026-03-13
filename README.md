# NotionOS — AI Agent Operating System for Notion

> Transform Notion into an autonomous command center. Create tasks in Notion and let AI agents plan, execute, and report back — automatically.

---

## Architecture

```
Notion Database
    ↓   (poll every 10s)
┌───────────────────────────────────────┐
│  FastAPI Backend                      │
│  ┌─────────────┐  ┌───────────────┐  │
│  │ Notion      │→ │ LangGraph     │  │
│  │ Watcher     │  │ Agent Engine  │  │
│  └─────────────┘  └──────┬────────┘  │
│                          │           │
│  ┌───────────────────────┴────────┐  │
│  │ Tool Layer                     │  │
│  │ Notion · GitHub · Gmail ·      │  │
│  │ Calendar · Playwright          │  │
│  └────────────────────────────────┘  │
│         ↓                            │
│  PostgreSQL (logs, agent runs)       │
│         ↓ WebSocket                  │
└───────────────────────────────────────┘
    ↓
Next.js Dashboard (real-time)
```

## Tech Stack

| Layer      | Technology              |
|------------|-------------------------|
| Backend    | Python · FastAPI        |
| Agent      | LangGraph · LangChain  |
| LLM        | Gemini 2.0 (Primary) · Groq (Fallback) |
| Automation | Playwright              |
| Database   | PostgreSQL · SQLAlchemy |
| Frontend   | Next.js · TailwindCSS   |
| Real-time  | WebSockets              |

---

## Quick Start

### 1. Clone & Environment

```bash
cp .env.example backend/.env
# Fill in your API keys in backend/.env
```

### 2. Set up PostgreSQL

```bash
createdb notionos
```

### 3. Start the Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install

# Run the server (from the project root, NOT backend/)
cd ..
uvicorn backend.main:app --reload
```

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:3000`.

---

## Tool Implementation Status

| Tool | Status | Implementation |
|------|--------|----------------|
| `search_jobs` | ✅ | Playwright Browser |
| `web_search` | ✅ | Tavily API (preferred) · Playwright fallback |
| `fill_forms` | ✅ | Playwright Browser |
| `update_notion_status` | ✅ | Notion API |
| `create_repo` | ✅ | GitHub API |
| `create_issue` | ✅ | GitHub API |
| `draft_email` | ⏳ | Stub (Auth needed) |
| `send_email` | ⏳ | Stub (Auth needed) |
| `schedule_event` | ⏳ | Stub (Auth needed) |
| `prepare_resume` | ⏳ | Stub |

---

## Status Vocabulary

### Backend (AgentRun Status)
- `PENDING`: Task detected, waiting for planner.
- `PLANNING`: LLM is generating the execution steps.
- `EXECUTING`: Tools are currently running.
- `COMPLETED`: All steps finished (even if some tools failed gracefully).
- `FAILED`: Planner failed or a critical system error occurred.

### Notion (AgentStatus Property)
- `Pending`: Set this to trigger the agent.
- `In Progress`: Agent is currently working.
- `COMPLETED`: Workflow finished successfully.
- `FAILED`: Workflow stopped due to an error.

---

## Environment Variables

### Backend (`backend/.env`)
- `GOOGLE_API_KEY`: Gemini API key from [AI Studio](https://aistudio.google.com/).
- `GROQ_API_KEY`: Groq API key from [Groq Console](https://console.groq.com/).
- `TAVILY_API_KEY`: Tavily API key for reliable web search results.
- `NOTION_API_KEY`: Internal integration secret.
- `NOTION_DATABASE_ID`: The 32-char ID of your task database.
- `GITHUB_TOKEN`: Personal access token with `repo` scope.
- `DATABASE_URL`: `postgresql://user:pass@localhost:5432/notionos`

### Frontend (`frontend/.env.local` - Optional)
- `NEXT_PUBLIC_API_URL`: Defaults to `http://localhost:8000`
- `NEXT_PUBLIC_WS_URL`: Defaults to `ws://localhost:8000`

---

## Repo Hygiene Note

The `frontend/` directory may contain its own `.git` folder depending on your initialization method. If you intend for this to be a single repository, you can safely delete `frontend/.git` and manage everything from the root.

---

## License

MIT
