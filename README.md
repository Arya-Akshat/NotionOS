# NotionOS

NotionOS turns a Notion database into a lightweight AI operations desk.

You create a task in Notion, mark it as `Pending`, and the backend watcher picks it up, plans the work, runs the available tools, writes progress to the database, and streams updates to a live dashboard.

This project is built as a practical prototype: it already connects real pieces together end-to-end, while a few integrations are still intentionally stubbed.

## What It Does

- Watches a Notion database for tasks that are ready to run
- Converts each task into a structured execution plan with a LangGraph workflow
- Executes supported tools like web search, form automation, and GitHub actions
- Stores run history and tool logs in the database
- Pushes live updates to a Next.js dashboard over WebSockets
- Writes status updates and result summaries back into Notion

## Demo

- Demo video: [demo.mp4](./demo.mp4)
- Screenshots are included near the bottom of this README

## How The Flow Works

1. A task is added in Notion and `AgentStatus` is set to `Pending`.
2. The FastAPI watcher polls Notion every 10 seconds.
3. The planner turns the task text into a goal plus a step-by-step execution plan.
4. The executor runs each tool, records outputs, retries failures when possible, and keeps going when a non-critical step fails.
5. Results are saved to the database, broadcast to the dashboard, and summarized back into the original Notion page.

## Tech Stack

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy, Uvicorn |
| Agent workflow | LangGraph, LangChain |
| LLM providers | Gemini (primary), Groq (configured as fallback) |
| Browser automation | Playwright |
| External integrations | Notion API, GitHub API, Tavily |
| Realtime | WebSockets |

## Project Structure

```text
.
├── backend/
│   ├── agent/          # intent parsing, planning, execution
│   ├── models/         # SQLAlchemy models for runs and tool logs
│   ├── tools/          # Notion, GitHub, browser, Gmail, calendar helpers
│   ├── workers/        # background Notion watcher
│   └── workflows/      # LangGraph task workflow
├── frontend/
│   └── src/            # dashboard UI
├── images/             # screenshots used in the README
└── demo.mp4            # demo video
```

## Current Feature Status

### Working in this repo

- `web_search`
- `search_jobs`
- `fill_forms`
- `update_notion_status`
- `create_issue`
- `github_open_pr`
- `github_pr_review_summary`
- live run tracking in the dashboard
- Notion result/status updates

### Present but still incomplete or auth-dependent

- `draft_email`
- `send_email`
- `schedule_event`
- `prepare_resume`
- any setup that depends on external secrets you have not configured yet

## Local Setup

### 1. Add environment variables

Copy the root example file into the backend:

```bash
cp .env.example backend/.env
```

Then fill in the values inside `backend/.env`.

Required keys:

- `GOOGLE_API_KEY`
- `GROQ_API_KEY`
- `TAVILY_API_KEY`
- `NOTION_API_KEY`
- `NOTION_DATABASE_ID`
- `GITHUB_TOKEN`
- `DATABASE_URL`

Default database value in the repo:

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/notionos"
```

### 2. Start PostgreSQL

Create a local database:

```bash
createdb notionos
```

### 3. Install backend dependencies

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install
```

### 4. Run the backend

From the project root:

```bash
uvicorn backend.main:app --reload
```

Backend endpoints:

- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- WebSocket: `ws://localhost:8000/ws/logs`

### 5. Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend:

- Dashboard: `http://localhost:3000`

## Expected Notion Setup

The watcher is expecting a Notion database with fields similar to these:

- `Name` or `Title`
- `Goal`
- `AgentStatus`

The workflow currently looks for rows where:

```text
AgentStatus = Pending
```

The code then updates that status throughout execution and appends a result summary back onto the page.

## Status Meanings

### Internal workflow status

- `PENDING`: run was created
- `PLANNING`: task is being converted into an execution plan
- `EXECUTING`: tool steps are currently running
- `COMPLETED`: execution finished
- `FAILED`: planning failed or a fatal error stopped the workflow

### Notion-facing status labels

- `Pending`
- `Planning`
- `In Progress`
- `Completed`
- `Failed`

## Notes And Tradeoffs

- The watcher polls every 10 seconds, so this is near-real-time rather than event-driven.
- The repo includes `backend/notionos.db`, but the app configuration defaults to PostgreSQL. The active database is whichever `DATABASE_URL` you set in `backend/.env`.
- Some integrations are clearly scaffolded for expansion, which makes this a strong prototype rather than a fully productized system.
- The dashboard is focused on visibility and debugging: runs, logs, statuses, and delete actions are all already wired up.

## Why This Project Is Interesting

What makes this project stand out is not just that it uses an LLM. The stronger idea is that Notion becomes the control surface for an agent system people already know how to use.

That makes the workflow feel approachable:

- product or ops people can trigger work from a familiar interface
- the backend keeps a structured log of what the agent actually did
- the dashboard gives the team a live operational view instead of a black box

## Screenshots

![Dashboard screenshot 1](images/Screenshot%202026-03-13%20at%206.58.45%E2%80%AFPM.png)
![Dashboard screenshot 2](images/Screenshot%202026-03-13%20at%206.58.55%E2%80%AFPM.png)
![Dashboard screenshot 3](images/Screenshot%202026-03-13%20at%206.59.03%E2%80%AFPM.png)
![Dashboard screenshot 4](images/Screenshot%202026-03-13%20at%206.59.25%E2%80%AFPM.png)
![Dashboard screenshot 5](images/Screenshot%202026-03-13%20at%206.59.57%E2%80%AFPM.png)
![Dashboard screenshot 6](images/Screenshot%202026-03-13%20at%207.00.03%E2%80%AFPM.png)
![Dashboard screenshot 7](images/Screenshot%202026-03-13%20at%207.00.06%E2%80%AFPM.png)

## License

MIT
