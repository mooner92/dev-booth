"use client";

import { useEffect, useRef, useState } from "react";
import { X, Github, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

interface NewSessionModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (name: string) => void;
}

function deriveSessionName(repoUrl: string): string {
  try {
    const url = new URL(repoUrl);
    const parts = url.pathname.replace(/^\//, "").replace(/\.git$/, "").split("/");
    const slug = parts[parts.length - 1] ?? "session";
    const date = new Date();
    const yyyymmdd = `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`;
    return `${slug}-${yyyymmdd}`.toLowerCase().replace(/[^a-z0-9-]/g, "-");
  } catch {
    return "";
  }
}

function isValidUrl(value: string): boolean {
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}

function isValidSessionName(value: string): boolean {
  return /^[a-z0-9-]+$/.test(value);
}

export function NewSessionModal({ open, onClose, onCreated }: NewSessionModalProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [sessionName, setSessionName] = useState("");
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameManual, setNameManual] = useState(false);

  const firstInputRef = useRef<HTMLInputElement>(null);

  // Auto-derive session name from repo URL unless user has manually edited it
  useEffect(() => {
    if (!nameManual && repoUrl) {
      const derived = deriveSessionName(repoUrl);
      if (derived) setSessionName(derived);
    }
  }, [repoUrl, nameManual]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  // Focus first input when opening
  useEffect(() => {
    if (open) {
      setTimeout(() => firstInputRef.current?.focus(), 50);
    } else {
      // Reset state when closed
      setRepoUrl("");
      setSessionName("");
      setGoal("");
      setLoading(false);
      setError(null);
      setNameManual(false);
    }
  }, [open]);

  if (!open) return null;

  const urlValid = isValidUrl(repoUrl);
  const nameValid = isValidSessionName(sessionName);
  const canSubmit = urlValid && nameValid && goal.trim().length > 0 && !loading;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      await api.startSession({ session_name: sessionName, repo_url: repoUrl, goal });
      onCreated(sessionName);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "알 수 없는 오류가 발생했습니다";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    // Backdrop — click outside to close
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-session-title"
    >
      <div className="relative w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <Github className="h-4 w-4 text-brand" />
            <h2 id="new-session-title" className="text-sm font-semibold text-foreground">
              새 작업 세션 시작
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="모달 닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mx-6 mt-4 flex items-start gap-2 rounded-lg border border-seed-error/40 bg-seed-error/10 px-3 py-2.5 text-xs text-seed-error">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-5 px-6 py-5">
          {/* Repo URL */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ns-repo-url" className="text-xs font-medium text-foreground">
              저장소 URL <span className="text-seed-error">*</span>
            </label>
            <input
              ref={firstInputRef}
              id="ns-repo-url"
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/org/repo.git"
              className={cn(
                "w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground/60",
                repoUrl && !urlValid
                  ? "border-seed-error focus:border-seed-error"
                  : "border-border focus:border-brand",
              )}
              autoComplete="off"
              spellCheck={false}
            />
            {repoUrl && !urlValid && (
              <span className="text-xs text-seed-error">올바른 URL을 입력해 주세요</span>
            )}
          </div>

          {/* Session name */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ns-session-name" className="text-xs font-medium text-foreground">
              세션 이름 <span className="text-seed-error">*</span>
            </label>
            <input
              id="ns-session-name"
              type="text"
              value={sessionName}
              onChange={(e) => { setSessionName(e.target.value); setNameManual(true); }}
              placeholder="my-repo-20260515"
              className={cn(
                "w-full rounded-lg border bg-background px-3 py-2 font-mono text-sm outline-none transition-colors placeholder:text-muted-foreground/60",
                sessionName && !nameValid
                  ? "border-seed-error focus:border-seed-error"
                  : "border-border focus:border-brand",
              )}
              autoComplete="off"
              spellCheck={false}
            />
            {sessionName && !nameValid && (
              <span className="text-xs text-seed-error">소문자, 숫자, 하이픈(-) 만 허용됩니다</span>
            )}
          </div>

          {/* Goal */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ns-goal" className="text-xs font-medium text-foreground">
              목표 <span className="text-seed-error">*</span>
            </label>
            <textarea
              id="ns-goal"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="이 세션에서 무엇을 달성하고 싶으신가요?"
              rows={3}
              className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-brand"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-muted-foreground hover:text-foreground"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-semibold transition-colors",
                canSubmit
                  ? "bg-brand text-white hover:bg-brand/90"
                  : "cursor-not-allowed bg-muted text-muted-foreground",
              )}
            >
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {loading ? "시작 중..." : "세션 시작"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
