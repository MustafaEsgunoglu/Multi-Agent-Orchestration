"use client";

import { Lock, Mail, Building2, UserPlus, LogIn } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { loginAccount, registerAccount } from "@/lib/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await registerAccount({
          email,
          password,
          full_name: fullName,
          organization_name: orgName,
        });
      } else {
        await loginAccount({ email, password });
      }
      router.push("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-950/95 p-8 shadow-2xl">
        <div className="mb-6 flex rounded-lg border border-slate-800 bg-slate-900 p-1 text-xs font-medium">
          <button
            type="button"
            onClick={() => setMode("register")}
            className={`flex-1 rounded-md py-2 transition ${
              mode === "register" ? "bg-sky-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Create Tenant Account
          </button>
          <button
            type="button"
            onClick={() => setMode("login")}
            className={`flex-1 rounded-md py-2 transition ${
              mode === "login" ? "bg-sky-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Sign In
          </button>
        </div>

        <h1 className="text-lg font-bold text-white">
          {mode === "register" ? "Create your Multi-Tenant Workspace" : "Welcome back"}
        </h1>
        <p className="mt-1 text-xs text-slate-400">
          {mode === "register"
            ? "Provisions an isolated PostgreSQL RLS tenant, default workspace, and signed JWT."
            : "Sign in to load your saved workflows and execution runs from Supabase."}
        </p>

        {error && (
          <div className="mt-4 rounded-lg border border-rose-500/40 bg-rose-950/40 px-3 py-2 text-xs text-rose-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-3.5 text-xs">
          {mode === "register" && (
            <>
              <div>
                <label className="mb-1 block font-medium text-slate-300">Full Name</label>
                <div className="flex items-center rounded-md border border-slate-700 bg-slate-900 px-3">
                  <UserPlus className="h-3.5 w-3.5 text-slate-500" />
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Mustafa Esgunoglu"
                    className="w-full bg-transparent px-2.5 py-2 text-slate-100 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block font-medium text-slate-300">Organization / Tenant</label>
                <div className="flex items-center rounded-md border border-slate-700 bg-slate-900 px-3">
                  <Building2 className="h-3.5 w-3.5 text-slate-500" />
                  <input
                    type="text"
                    required
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    placeholder="Acme AI Lab"
                    className="w-full bg-transparent px-2.5 py-2 text-slate-100 focus:outline-none"
                  />
                </div>
              </div>
            </>
          )}

          <div>
            <label className="mb-1 block font-medium text-slate-300">Email</label>
            <div className="flex items-center rounded-md border border-slate-700 bg-slate-900 px-3">
              <Mail className="h-3.5 w-3.5 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full bg-transparent px-2.5 py-2 text-slate-100 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block font-medium text-slate-300">Password</label>
            <div className="flex items-center rounded-md border border-slate-700 bg-slate-900 px-3">
              <Lock className="h-3.5 w-3.5 text-slate-500" />
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min 8 characters"
                className="w-full bg-transparent px-2.5 py-2 text-slate-100 focus:outline-none"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-sky-600 py-2.5 font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50"
          >
            {mode === "register" ? <UserPlus className="h-4 w-4" /> : <LogIn className="h-4 w-4" />}
            {loading
              ? "Please wait..."
              : mode === "register"
                ? "Create Account & Workspace"
                : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
