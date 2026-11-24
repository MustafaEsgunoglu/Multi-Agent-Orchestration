"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";

import { WorkflowCanvas } from "@/components/canvas/WorkflowCanvas";
import { CopilotSidebar } from "@/components/copilot/CopilotSidebar";
import { NodeInspector } from "@/components/panels/NodeInspector";
import { useWorkflowStore } from "@/stores/workflowStore";

export default function StudioPage() {
  const params = useParams<{ workflowId: string }>();
  const loadTemplateById = useWorkflowStore((s) => s.loadTemplateById);

  useEffect(() => {
    if (params?.workflowId) {
      loadTemplateById(params.workflowId);
    }
  }, [params?.workflowId, loadTemplateById]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] w-full overflow-hidden">
      <CopilotSidebar />
      <WorkflowCanvas />
      <NodeInspector />
    </div>
  );
}
