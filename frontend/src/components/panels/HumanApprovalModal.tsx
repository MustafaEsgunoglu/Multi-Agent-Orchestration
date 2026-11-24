"use client";

import { Check, Edit3, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";

export interface PendingApprovalState {
  mode: "saved" | "dev";
  runOrThreadId: string;
  nodeId: string;
  label: string;
  promptMessage: string;
  lastOutput: string;
  allowedActions: ("approve" | "reject" | "edit")[];
}

interface HumanApprovalModalProps {
  pending: PendingApprovalState;
  submitting: boolean;
  onDecision: (action: "approve" | "reject" | "edit", editedOutput?: string) => void;
  onClose: () => void;
}

export function HumanApprovalModal({
  pending,
  submitting,
  onDecision,
  onClose,
}: HumanApprovalModalProps) {
  const [editedText, setEditedText] = useState(pending.lastOutput);

  useEffect(() => {
    setEditedText(pending.lastOutput);
  }, [pending.lastOutput, pending.runOrThreadId]);

  const canApprove = pending.allowedActions.includes("approve");
  const canEdit = pending.allowedActions.includes("edit");
  const canReject = pending.allowedActions.includes("reject");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-fuchsia-500/40 bg-slate-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-fuchsia-500/20 text-fuchsia-300">
              <ShieldAlert className="h-4 w-4" />
            </span>
            <div>
              <h3 className="text-sm font-bold text-white">
                Human-in-the-Loop Approval — {pending.label}
              </h3>
              <p className="text-[11px] text-slate-400">
                LangGraph checkpoint paused at node{" "}
                <span className="font-mono text-fuchsia-300">{pending.nodeId}</span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-5 text-xs">
          <div className="rounded-lg border border-fuchsia-500/20 bg-fuchsia-950/20 px-3.5 py-2.5 text-fuchsia-200">
            {pending.promptMessage}
          </div>

          <div>
            <label className="mb-1.5 block font-medium text-slate-300">
              Agent Output (review or edit before resuming)
            </label>
            <textarea
              rows={8}
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
              disabled={!canEdit}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 p-3 font-sans text-xs leading-relaxed text-slate-100 focus:border-fuchsia-500 focus:outline-none disabled:opacity-75"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-800 px-5 py-3.5">
          {canReject && (
            <button
              type="button"
              disabled={submitting}
              onClick={() => onDecision("reject")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-950/40 px-3.5 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-900/50 disabled:opacity-50"
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </button>
          )}

          {canEdit && (
            <button
              type="button"
              disabled={submitting}
              onClick={() => onDecision("edit", editedText)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-950/40 px-3.5 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-900/50 disabled:opacity-50"
            >
              <Edit3 className="h-3.5 w-3.5" />
              Save Edit & Continue
            </button>
          )}

          {canApprove && (
            <button
              type="button"
              disabled={submitting}
              onClick={() => onDecision("approve")}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              {submitting ? "Resuming..." : "Approve & Continue"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
