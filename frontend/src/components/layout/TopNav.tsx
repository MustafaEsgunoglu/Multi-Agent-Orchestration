"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import {
  LAST_WORKFLOW_STORAGE_KEY,
  useWorkflowStore,
  WORKFLOW_TEMPLATES,
} from "@/stores/workflowStore";

export function TopNav() {
  const pathname = usePathname();
  const activeWorkflowId = useWorkflowStore((s) => s.activeWorkflowId);
  const workflowName = useWorkflowStore((s) => s.workflowName);
  const [lastWorkflowId, setLastWorkflowId] = useState<string>("starter");

  useEffect(() => {
    const stored = window.localStorage.getItem(LAST_WORKFLOW_STORAGE_KEY);
    if (stored && stored in WORKFLOW_TEMPLATES) {
      setLastWorkflowId(stored);
    }
  }, []);

  useEffect(() => {
    if (activeWorkflowId && activeWorkflowId in WORKFLOW_TEMPLATES) {
      setLastWorkflowId(activeWorkflowId);
    }
  }, [activeWorkflowId]);

  const isStudio = pathname.startsWith("/studio");

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6">
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-sky-600 text-xs font-bold text-white">
            MA
          </span>
          <span className="text-sm text-slate-100">Multi-Agent Orchestrator</span>
        </Link>

        {isStudio && (
          <>
            <span className="text-slate-600">/</span>
            <div className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span className="max-w-[260px] truncate text-xs font-semibold text-slate-100">
                {workflowName}
              </span>
            </div>
          </>
        )}
      </div>

      <nav className="flex items-center gap-5 text-xs font-medium text-slate-300">
        <Link
          href="/"
          className={pathname === "/" ? "text-sky-400" : "hover:text-sky-400"}
        >
          Dashboard
        </Link>
        <Link
          href={`/studio/${lastWorkflowId}`}
          className={isStudio ? "text-sky-400" : "hover:text-sky-400"}
        >
          Visual Studio
        </Link>
        <Link
          href="/runs"
          className={pathname === "/runs" ? "text-sky-400" : "hover:text-sky-400"}
        >
          Execution Runs
        </Link>
      </nav>
    </header>
  );
}
