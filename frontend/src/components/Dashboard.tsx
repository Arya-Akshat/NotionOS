"use client";

import { useEffect, useState, useRef, useCallback } from "react";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type AgentRun = {
  id: number;
  notion_task_id: string;
  status: string;
  goal: string | null;
  execution_plan: any[] | null;
  created_at: string;
  updated_at: string;
};

type ToolLog = {
  id: number;
  tool_name: string;
  tool_input: Record<string, unknown> | null;
  status: string;
  tool_output: Record<string, unknown> | null;
  error_message: string | null;
  duration_ms: number | null;
  created_at: string;
};

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

const STATUS_COLORS: Record<string, string> = {
  PENDING:   "bg-amber-500/20 text-amber-400 border-amber-500/50",
  PLANNING:  "bg-violet-500/20 text-violet-400 border-violet-500/50",
  EXECUTING: "bg-blue-500/20 text-blue-400 border-blue-500/50",
  COMPLETED: "bg-emerald-500/20 text-emerald-400 border-emerald-500/50",
  FAILED:    "bg-red-500/20 text-red-400 border-red-500/50",
};

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function Dashboard() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const [logs, setLogs] = useState<ToolLog[]>([]);
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected">("disconnected");
  const [deletingRunId, setDeletingRunId] = useState<number | null>(null);
  
  // Refs to handle stale closures in WebSocket callbacks
  // Refs to handle stale closures and lifecycle
  const isMounted = useRef(false);
  const selectedRunRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);

  useEffect(() => {
    selectedRunRef.current = selectedRun;
  }, [selectedRun]);

  /* ---- Fetch agent runs ------------------------------------------ */
  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/runs`);
      if (res.ok) {
        const data = await res.json();
        setRuns(data);
      }
    } catch (err) {
      console.error("Failed to fetch runs:", err);
    }
  }, []);

  /* ---- Fetch logs for a selected run ----------------------------- */
  const fetchLogs = useCallback(async (runId: number) => {
    try {
      const res = await fetch(`${API_URL}/api/runs/${runId}/logs`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data);
      }
    } catch (err) {
      console.error("Failed to fetch logs:", err);
    }
  }, []);

  /* ---- Delete a run --------------------------------------------- */
  const deleteRun = useCallback(async (runId: number) => {
    try {
      setDeletingRunId(runId);
      const res = await fetch(`${API_URL}/api/runs/${runId}`, { method: "DELETE" });
      if (!res.ok) {
        throw new Error(`Delete failed with status ${res.status}`);
      }

      setRuns((currentRuns) => currentRuns.filter((run) => run.id !== runId));

      if (selectedRunRef.current === runId) {
        selectedRunRef.current = null;
        setSelectedRun(null);
        setLogs([]);
      }
    } catch (err) {
      console.error("Failed to delete run:", err);
    } finally {
      setDeletingRunId(null);
    }
  }, []);

  /* ---- WebSocket setup ------------------------------------------- */
  const connectWebSocket = useCallback(() => {
    // Component lifecycle check
    if (!isMounted.current) return;

    const ws = new WebSocket(`${WS_URL}/ws/logs`);

    ws.onopen = () => {
      console.log("WebSocket connected");
      setWsStatus("connected");
      reconnectAttemptsRef.current = 0;
      fetchRuns();
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      setWsStatus("disconnected");
      
      if (!isMounted.current) return;

      // Exponential backoff for reconnection
      const timeout = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
      reconnectTimeoutRef.current = setTimeout(() => {
        if (isMounted.current) {
          reconnectAttemptsRef.current += 1;
          connectWebSocket();
        }
      }, timeout);
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      ws.close();
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("WS Message:", data);

      if (data.type === "run_deleted") {
        setRuns((currentRuns) => currentRuns.filter((run) => run.id !== data.run_id));
        if (selectedRunRef.current === data.run_id) {
          selectedRunRef.current = null;
          setSelectedRun(null);
          setLogs([]);
        }
        return;
      }
      
      // Refresh runs list
      fetchRuns();
      
      // If the current message pertains to the selected run, refresh logs
      if (selectedRunRef.current === data.run_id && selectedRunRef.current !== null) {
        fetchLogs(selectedRunRef.current);
      }
    };

    wsRef.current = ws;
  }, [fetchRuns, fetchLogs]);

  useEffect(() => {
    isMounted.current = true;
    connectWebSocket();

    // Fallback polling every 30s instead of 5s to reduce noise,
    // since we have real-time updates.
    const pollInterval = setInterval(fetchRuns, 30000);

    return () => {
      isMounted.current = false;
      clearInterval(pollInterval);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connectWebSocket, fetchRuns]);

  useEffect(() => {
    if (selectedRun) fetchLogs(selectedRun);
  }, [selectedRun, fetchLogs]);

  /* ---- Render ---------------------------------------------------- */
  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 md:p-10 font-sans">
      {/* Header */}
      <header className="mb-10 flex items-center justify-between border-b border-gray-800 pb-6">
        <div>
          <h1 className="text-4xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-violet-400 to-emerald-400">
            NotionOS
          </h1>
          <p className="text-gray-500 mt-1 text-sm">AI Agent Command Center</p>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={fetchRuns}
            className="text-xs bg-gray-800 hover:bg-gray-700 px-3 py-1 rounded-full border border-gray-700 transition-colors"
          >
            Refresh
          </button>
          <span
            className={`text-xs px-3 py-1 rounded-full border ${
              wsStatus === "connected"
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/40"
                : "bg-red-500/10 text-red-400 border-red-500/40"
            }`}
          >
            ● {wsStatus === "connected" ? "Live" : "Disconnected (Reconnecting...)"}
          </span>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
        {/* ---- Active workflows ---- */}
        <section className="lg:col-span-2 bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl">
          <h2 className="text-lg font-semibold text-blue-300 mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
            Agent Runs
          </h2>

          {runs.length === 0 && (
            <p className="text-gray-600 text-sm italic">No runs detected. Create a task in Notion and set AgentStatus to 'Pending'.</p>
          )}

          <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
            {runs.map((r) => (
              <div
                key={r.id}
                onClick={() => setSelectedRun(r.id)}
                className={`w-full text-left p-4 rounded-xl border transition-all duration-200 ${
                  selectedRun === r.id
                    ? "bg-gray-800 border-blue-500/60 shadow-lg shadow-blue-500/10"
                    : "bg-gray-800/40 border-gray-700 hover:border-gray-600"
                }`}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelectedRun(r.id);
                  }
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate text-gray-100">{r.goal || "Planning..."}</p>
                    <p className="text-[10px] text-gray-500 mt-1 uppercase tracking-tight">
                       ID: {r.notion_task_id.substring(0, 8)}...
                    </p>
                  </div>
                  <div className="flex items-start gap-2">
                    <span
                      className={`shrink-0 text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full border ${
                        STATUS_COLORS[r.status] ?? "bg-gray-700 text-gray-300 border-gray-600"
                      }`}
                    >
                      {r.status}
                    </span>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void deleteRun(r.id);
                      }}
                      disabled={deletingRunId === r.id}
                      className="shrink-0 rounded-full border border-red-500/30 bg-red-500/10 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-red-300 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {deletingRunId === r.id ? "Deleting" : "Delete"}
                    </button>
                  </div>
                </div>
                <div className="mt-3 overflow-hidden">
                   <div className="text-[10px] text-gray-500 font-mono items-center flex gap-1">
                     <span className="text-gray-600">Plan:</span>
                     <span className="truncate">
                       {r.execution_plan?.map((p: any) => typeof p === 'string' ? p : p.tool).join(" → ") || "Waiting for planner..."}
                     </span>
                   </div>
                </div>
                <p className="text-[10px] text-gray-600 mt-2">
                  {new Date(r.created_at).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ---- Execution logs ---- */}
        <section className="lg:col-span-3 bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl">
          <h2 className="text-lg font-semibold text-emerald-300 mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            Step Details
          </h2>

          {!selectedRun ? (
            <div className="h-full flex items-center justify-center text-gray-600 text-sm italic">
              Select an agent run to view granular execution logs.
            </div>
          ) : (
            <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
              {logs.length === 0 && (
                <div className="text-gray-600 text-sm italic py-10 text-center">
                  No steps recorded yet for this run.
                </div>
              )}
              {logs.map((l) => (
                <div
                  key={l.id}
                  className="p-4 rounded-xl bg-gray-800/40 border border-gray-700/50 hover:border-gray-600 transition-colors"
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-blue-300 font-bold font-mono text-sm">{l.tool_name}</span>
                      {l.duration_ms && (
                        <span className="text-gray-600 text-[10px] font-mono">{l.duration_ms}ms</span>
                      )}
                    </div>
                    <span
                      className={`text-[10px] font-black uppercase px-2 py-0.5 rounded border ${
                        l.status === "success" 
                          ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/5" 
                          : "text-red-400 border-red-500/30 bg-red-500/5"
                      }`}
                    >
                      {l.status}
                    </span>
                  </div>
                  
                  {/* Tool Input */}
                  {l.tool_input && Object.keys(l.tool_input).length > 0 && (
                    <div className="mb-2">
                      <span className="text-[10px] text-gray-600 uppercase font-bold tracking-widest block mb-1">Input params</span>
                      <pre className="text-[11px] bg-black/30 p-2 rounded text-gray-400 overflow-x-auto">
                        {JSON.stringify(l.tool_input, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Tool Output / Error */}
                  {l.error_message ? (
                    <div className="p-2 rounded bg-red-900/10 border border-red-500/20">
                      <p className="text-red-400 text-xs font-mono">
                        <span className="font-bold mr-1">Error:</span>
                        {l.error_message}
                      </p>
                    </div>
                  ) : l.tool_output && (
                    <div>
                      <span className="text-[10px] text-gray-600 uppercase font-bold tracking-widest block mb-1">Result</span>
                      <pre className="text-[11px] bg-black/20 p-2 rounded text-emerald-400/80 overflow-x-auto">
                        {JSON.stringify(l.tool_output, null, 2)}
                      </pre>
                    </div>
                  )}
                  
                  <div className="text-right mt-3">
                    <span className="text-gray-600 text-[9px] uppercase">
                      {new Date(l.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
