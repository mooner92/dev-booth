"use client";

import { cn } from "@/lib/utils";
import { useKanban, type KanbanTask, type TaskStatus } from "@/hooks/useKanban";
import { AGENT_COLORS } from "@/lib/constants";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

/** Strip "[repo-name] " prefix from task titles for compact sidebar display. */
export function trimTaskTitle(title: string): string {
  return title.replace(/^\[[^\]]+\]\s*/, "");
}

// ── StatusIcon ─────────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case "done":
      return <span className="text-emerald-500">✓</span>;
    case "running":
      return (
        <span className="relative inline-flex h-2 w-2">
          <span className="absolute h-full w-full animate-ping rounded-full bg-brand opacity-75" />
          <span className="relative h-2 w-2 rounded-full bg-brand" />
        </span>
      );
    case "blocked":
      return (
        <span className="relative inline-flex h-2 w-2 items-center justify-center">
          <span className="absolute h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
          <span className="relative text-amber-500">⊘</span>
        </span>
      );
    case "ready":
      return <span className="text-blue-500">▶</span>;
    default:
      return (
        <span className="inline-block h-2 w-2 rounded border border-muted-foreground/30" />
      );
  }
}

// ── TaskRow ────────────────────────────────────────────────────────────────────

function TaskRow({
  task,
  selected,
  onSelect,
}: {
  task: KanbanTask;
  selected: boolean;
  onSelect?: (id: string) => void;
}) {
  const agentColor = task.assignee
    ? (AGENT_COLORS[task.assignee] ?? "#6B7280")
    : null;

  return (
    <button
      type="button"
      onClick={() => onSelect?.(task.id)}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-muted",
        selected && "border-l-2 border-brand bg-muted",
      )}
    >
      <span className="flex w-3 shrink-0 items-center justify-center text-xs">
        <StatusIcon status={task.status} />
      </span>
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-xs leading-snug",
          task.status === "done" && "text-muted-foreground line-through",
          task.status === "running" && "font-medium text-foreground",
          task.status === "blocked" && "text-amber-600 dark:text-amber-400",
        )}
        title={task.title}
      >
        {trimTaskTitle(task.title)}
      </span>
      {agentColor && (
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: agentColor }}
        />
      )}
    </button>
  );
}

// ── GpuSummary ────────────────────────────────────────────────────────────────
// Mirrors MonitoringPane's api.getMetricsPreset pattern with a 5s polling loop.

function GpuSummary() {
  const [util, setUtil] = useState<number | null>(null);
  const [memMiB, setMem] = useState<number | null>(null);
  const [tempC, setTemp] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const [u, m, t] = await Promise.all([
          api.getMetricsPreset("gpu_utilization").catch(() => null),
          api.getMetricsPreset("gpu_memory_used").catch(() => null),
          api.getMetricsPreset("gpu_temperature").catch(() => null),
        ]);
        if (cancelled) return;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const v = (snap: any) =>
          snap?.available
            ? (Object.values(snap.series)[0] as { points: [number, number][] } | undefined)
                ?.points[0]?.[1] ?? null
            : null;
        setUtil(v(u));
        setMem(v(m));
        setTemp(v(t));
      } catch {
        /* swallow — GPU panel is best-effort */
      }
    }

    tick();
    const id = window.setInterval(tick, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (util === null && memMiB === null && tempC === null) return null;

  const utilColor = (util ?? 0) > 80 ? "text-red-500" : "text-emerald-500";
  const tempColor = (tempC ?? 0) > 80 ? "text-red-500" : "text-foreground";

  return (
    <div className="shrink-0 space-y-1 border-t border-border px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        GPU
      </p>
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">사용률</span>
        <span className={cn("font-mono", utilColor)}>
          {util != null ? `${util.toFixed(0)}%` : "—"}
        </span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">메모리</span>
        <span className="font-mono text-foreground">
          {memMiB != null ? `${Math.round(memMiB)} MiB` : "—"}
        </span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">온도</span>
        <span className={cn("font-mono", tempColor)}>
          {tempC != null ? `${tempC.toFixed(0)}°C` : "—"}
        </span>
      </div>
    </div>
  );
}

// ── KanbanBoard ───────────────────────────────────────────────────────────────

export function KanbanBoard({
  boardSlug,
  selectedTaskId,
  onTaskSelect,
}: {
  boardSlug: string;
  selectedTaskId?: string;
  onTaskSelect?: (id: string) => void;
}) {
  const { tasks, stats, connected } = useKanban(boardSlug);

  const sorted = [...tasks].sort(
    (a, b) => (a.created_at ?? 0) - (b.created_at ?? 0),
  );
  const doneCount = sorted.filter((t) => t.status === "done").length;

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      {/* Header */}
      <div className="shrink-0 border-b border-border px-3 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Kanban
          </h2>
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              connected ? "bg-emerald-500" : "bg-neutral-300",
            )}
            title={connected ? "WS connected" : "WS reconnecting"}
          />
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          완료 {doneCount} / 전체 {sorted.length}
          {stats && (
            <span className="ml-2 text-[10px]">
              · 실행 {stats.running}
              {stats.blocked > 0 && ` · 차단 ${stats.blocked}`}
            </span>
          )}
        </p>
      </div>

      {/* Task list */}
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {sorted.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            작업이 없습니다.
          </p>
        ) : (
          sorted.map((t) => (
            <TaskRow
              key={t.id}
              task={t}
              selected={t.id === selectedTaskId}
              onSelect={onTaskSelect}
            />
          ))
        )}
      </div>

      {/* GPU summary footer */}
      <GpuSummary />
    </div>
  );
}
