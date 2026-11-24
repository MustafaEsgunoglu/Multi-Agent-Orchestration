"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";

import { WorkflowCanvas } from "@/components/canvas/WorkflowCanvas";
import { CopilotSidebar } from "@/components/copilot/CopilotSidebar";
import { NodeInspector } from "@/components/panels/NodeInspector";
import { getStoredToken, getWorkflowById } from "@/lib/api";
import { useWorkflowStore } from "@/stores/workflowStore";

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function StudioPage() {
  const params = useParams<{ workflowId: string }>();
  const loadTemplateById = useWorkflowStore((s) => s.loadTemplateById);
  const loadSavedWorkflow = useWorkflowStore((s) => s.loadSavedWorkflow);

  useEffect(() => {
    const wfId = params?.workflowId;
    if (!wfId) return;

    if (UUID_REGEX.test(wfId) && getStoredToken()) {
      void getWorkflowById(wfId)
        .then((rec) =>
          loadSavedWorkflow({
            id: rec.id,
            name: rec.name,
            definition: rec.definition,
          }),
        )
        .catch(() => loadTemplateById("starter"));
    } else {
      loadTemplateById(wfId);
    }
  }, [params?.workflowId, loadTemplateById, loadSavedWorkflow]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full overflow-hidden">
      <CopilotSidebar />
      <WorkflowCanvas />
      <NodeInspector />
    </div>
  );
}
