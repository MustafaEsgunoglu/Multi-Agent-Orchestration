import type { Metadata } from "next";

import { TopNav } from "@/components/layout/TopNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orchestrator Studio — Multi-Agent No-Code Platform",
  description: "Multi-tenant visual LangGraph orchestration studio with RAG, MCP & HITL.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="flex min-h-screen flex-col bg-[#0b0f19] text-slate-100">
        <TopNav />
        <main className="flex flex-1 flex-col">{children}</main>
      </body>
    </html>
  );
}
