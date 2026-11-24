"use client";

import { Check, ChevronDown, LogIn, LogOut, User } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  clearStoredToken,
  getMe,
  getStoredToken,
  listWorkflows,
  UserMeRecord,
  WorkflowRecord,
} from "@/lib/api";
import {
  LAST_WORKFLOW_STORAGE_KEY,
  useWorkflowStore,
  WORKFLOW_TEMPLATES,
} from "@/stores/workflowStore";

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const activeWorkflowId = useWorkflowStore((s) => s.activeWorkflowId);
  const workflowName = useWorkflowStore((s) => s.workflowName);
  const setWorkflowName = useWorkflowStore((s) => s.setWorkflowName);

  const [lastWorkflowId, setLastWorkflowId] = useState<string>("starter");
  const [user, setUser] = useState<UserMeRecord | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [savedWorkflows, setSavedWorkflows] = useState<WorkflowRecord[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(LAST_WORKFLOW_STORAGE_KEY);
    if (stored) setLastWorkflowId(stored);
    void getMe().then(setUser);
  }, [pathname]);

  useEffect(() => {
    if (activeWorkflowId) {
      setLastWorkflowId(activeWorkflowId);
    }
  }, [activeWorkflowId]);

  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener("mousedown", handleOutsideClick);
    }
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [menuOpen]);

  async function toggleSwitcher() {
    const nextOpen = !menuOpen;
    setMenuOpen(nextOpen);
    if (nextOpen && getStoredToken()) {
      setLoadingList(true);
      try {
        const rows = await listWorkflows();
        setSavedWorkflows(rows);
      } catch {
        setSavedWorkflows([]);
      } finally {
        setLoadingList(false);
      }
    }
  }

  function handleSelectWorkflow(id: string) {
    setMenuOpen(false);
    router.push(`/studio/${id}`);
  }

  function handleSignOut() {
    clearStoredToken();
    setUser(null);
    setSavedWorkflows([]);
    router.push("/");
    router.refresh();
  }

  const isStudio = pathname.startsWith("/studio");

  return (
    <header className="relative z-40 flex h-14 items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6">
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
            <div ref={dropdownRef} className="relative">
              <div className="flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900 pl-2.5 pr-1 py-1">
                <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  aria-label="Workflow name"
                  className="w-48 bg-transparent text-xs font-semibold text-slate-100 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => void toggleSwitcher()}
                  title="Switch workflow"
                  className="inline-flex h-6 w-6 items-center justify-center rounded text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
                >
                  <ChevronDown
                    className={`h-3.5 w-3.5 transition-transform ${menuOpen ? "rotate-180" : ""}`}
                  />
                </button>
              </div>

              {menuOpen && (
                <div className="absolute left-0 top-full mt-1.5 w-72 overflow-hidden rounded-xl border border-slate-800 bg-slate-950 shadow-2xl">
                  {user && (
                    <div className="border-b border-slate-800 p-1.5">
                      <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
                        Saved Workflows (Supabase)
                      </div>
                      {loadingList ? (
                        <div className="px-2.5 py-2 text-xs text-slate-500">Loading...</div>
                      ) : savedWorkflows.length === 0 ? (
                        <div className="px-2.5 py-2 text-xs text-slate-500">
                          No saved workflows yet
                        </div>
                      ) : (
                        <div className="max-h-52 overflow-y-auto">
                          {savedWorkflows.map((wf) => (
                            <button
                              key={wf.id}
                              type="button"
                              onClick={() => handleSelectWorkflow(wf.id)}
                              className="flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-slate-200 transition hover:bg-slate-800/80"
                            >
                              <div className="min-w-0 flex-1">
                                <div className="truncate font-medium">{wf.name}</div>
                                <div className="text-[10px] text-slate-500">
                                  v{wf.version} · {wf.definition.nodes.length} nodes
                                </div>
                              </div>
                              {activeWorkflowId === wf.id && (
                                <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="p-1.5">
                    <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      Starter Templates
                    </div>
                    {Object.entries(WORKFLOW_TEMPLATES).map(([id, tpl]) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => handleSelectWorkflow(id)}
                        className="flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-slate-300 transition hover:bg-slate-800/80"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium">{tpl.name}</div>
                          <div className="text-[10px] text-slate-500">
                            {tpl.definition.nodes.length} nodes
                          </div>
                        </div>
                        {activeWorkflowId === id && (
                          <Check className="h-3.5 w-3.5 shrink-0 text-sky-400" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <nav className="flex items-center gap-5 text-xs font-medium text-slate-300">
        <Link href="/" className={pathname === "/" ? "text-sky-400" : "hover:text-sky-400"}>
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

        {user ? (
          <div className="flex items-center gap-2 border-l border-slate-800 pl-4">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-2.5 py-1 text-slate-200">
              <User className="h-3.5 w-3.5 text-emerald-400" />
              {user.full_name}
            </span>
            <button
              type="button"
              onClick={handleSignOut}
              title="Sign Out"
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-slate-300 hover:border-rose-500/50 hover:text-rose-300"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          <Link
            href="/auth"
            className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 font-semibold text-white hover:bg-sky-500"
          >
            <LogIn className="h-3.5 w-3.5" />
            Sign In
          </Link>
        )}
      </nav>
    </header>
  );
}
