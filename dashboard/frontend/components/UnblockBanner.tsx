"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

interface UnblockBannerProps {
  boardSlug: string;
  taskId: string;
  taskTitle: string;
  onUnblocked?: () => void;
}

export function UnblockBanner({
  boardSlug,
  taskId,
  taskTitle,
  onUnblocked,
}: UnblockBannerProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function handleUnblock() {
    setLoading(true);
    setError("");
    try {
      await api.unblockTask(boardSlug, taskId);
      setDone(true);
      onUnblocked?.();
    } catch (e) {
      const msg =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : "오류 발생";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="flex items-center gap-2 border-b border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-xs text-emerald-400">
        ✅ 재시작됨 — 에이전트가 곧 작업을 이어받습니다
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 border-b border-amber-500/20 bg-amber-500/10 px-4 py-2">
      <span className="text-sm text-amber-500">⊘</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-amber-400">
          차단됨: {taskTitle}
        </p>
        {error && <p className="mt-0.5 text-xs text-red-400">{error}</p>}
      </div>
      <button
        type="button"
        onClick={handleUnblock}
        disabled={loading}
        className={cn(
          "shrink-0 rounded-lg bg-amber-500 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-amber-400",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        {loading ? "처리 중..." : "🔓 재시작"}
      </button>
    </div>
  );
}
