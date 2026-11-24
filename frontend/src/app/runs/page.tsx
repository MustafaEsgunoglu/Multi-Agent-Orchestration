"use client";

import { Activity, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { ExecutionRunRecord, listExecutionRuns } from "@/lib/api";

export default function RunsPage() {
  const [runs, setRuns] = useState<ExecutionRunRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadRuns() {
    setLoading(true);
    setError(null);
    try {
      const data = await listExecutionRuns();
      setRuns(data);
    } catch {
      setError("Sign in and start the FastAPI backend (:8000) to view tenant execution runs.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRuns();
  }, []);

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Activity className="h-5 w-5 text-sky-400" />
          <h1 className="text-xl font-bold text-white">Execution Runs & Cost Telemetry</h1>
        </div>
        <button
          type="button"
          onClick={() => void loadRuns()}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-950/30 px-4 py-3 text-xs text-amber-300">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-800 bg-slate-950/80 text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium">Run ID</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Tokens</th>
              <th className="px-4 py-3 font-medium">Est. Cost (USD)</th>
              <th className="px-4 py-3 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  Loading execution runs...
                </td>
              </tr>
            ) : runs.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No execution runs recorded yet.
                </td>
              </tr>
            ) : (
              runs.map((run) => (
                <tr key={run.id} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-mono text-slate-200">{run.id.slice(0, 8)}...</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-slate-800 px-2.5 py-0.5 font-medium text-sky-300">
                      {run.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{run.total_tokens}</td>
                  <td className="px-4 py-3 font-mono text-emerald-400">
                    ${Number(run.estimated_cost_usd).toFixed(6)}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
