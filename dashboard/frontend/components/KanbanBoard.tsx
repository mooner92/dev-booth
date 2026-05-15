"use client";

import { cn } from "@/lib/utils";
import { useKanban, type KanbanTask, type KanbanStats, type TaskStatus } from "@/hooks/useKanban";
import { AGENT_COLORS, AGENT_LABELS } from "@/lib/constants";
import { Circle } from "lucide-react";

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_ORDER: TaskStatus[] = [
  "triage",
  "todo",
  "ready",
  "running",
  "blocked",
  "done",
  "archived",
];

const STATUS_LABELS: Record<TaskStatus, string> = {
  triage: "분류 중",
  todo: "할 일",
  ready: "준비됨",
  running: "실행 중",
  blocked: "차단됨",
  done: "완료",
  archived: "보관됨",
};

// Tailwind classes per status (badge bg + text)
const STATUS_BADGE: Record<TaskStatus, string> = {
  triage: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
  todo: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
  ready: "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  running: "bg-brand-50 text-brand-700 dark:bg-brand-900 dark:text-brand-300",
  blocked: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  done: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  archived: "bg-neutral-100 text-neutral-400 dark:bg-neutral-900 dark:text-neutral-600",
};

// ── Stats strip ───────────────────────────────────────────────────────────────

function StatsStrip({ stats }: { stats: KanbanStats }) {
  const items: { status: TaskStatus; count: number }[] = [
    { status: "triage", count: stats.triage },
    { status: "todo", count: stats.todo },
    { status: "ready", count: stats.ready },
    { status: "running", count: stats.running },
    { status: "blocked", count: stats.blocked },
    { status: "done", count: stats.done },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {items.map(({ status, count }) => (
        <span
          key={status}
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            STATUS_BADGE[status],
          )}
        >
          {STATUS_LABELS[status]}
          <span className="font-bold">{count}</span>
        </span>
      ))}
    </div>
  );
}

// ── Running indicator ─────────────────────────────────────────────────────────

function RunningDot() {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-block h-2 w-2 rounded-full bg-brand animate-pulse-dot" />
      <span className="text-xs text-brand-600 dark:text-brand-400 font-medium">에이전트 작업 중</span>
    </span>
  );
}

// ── Task card ─────────────────────────────────────────────────────────────────

function TaskCard({ task }: { task: KanbanTask }) {
  const agentColor = task.assignee ? (AGENT_COLORS[task.assignee] ?? "#6B7280") : "#6B7280";
  const agentLabel = task.assignee ? (AGENT_LABELS[task.assignee] ?? task.assignee) : null;

  return (
    <div className="rounded border border-border bg-background px-3 py-2.5 shadow-card space-y-1.5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium leading-snug text-foreground line-clamp-2">
          {task.title}
        </span>
        <span
          className={cn(
            "shrink-0 inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-medium",
            STATUS_BADGE[task.status],
          )}
        >
          {STATUS_LABELS[task.status]}
        </span>
      </div>
      {task.status === "running" && <RunningDot />}
      {agentLabel && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Circle className="h-2 w-2 fill-current" style={{ color: agentColor }} />
          {agentLabel}
        </div>
      )}
    </div>
  );
}

// ── Column ────────────────────────────────────────────────────────────────────

function Column({ status, tasks }: { status: TaskStatus; tasks: KanbanTask[] }) {
  if (tasks.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold", STATUS_BADGE[status])}>
          {STATUS_LABELS[status]}
        </span>
        <span className="text-xs text-muted-foreground">{tasks.length}</span>
      </div>
      <div className="space-y-2">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function KanbanBoard({ boardSlug }: { boardSlug: string }) {
  const { tasks, stats, connected } = useKanban(boardSlug);

  const grouped = STATUS_ORDER.reduce<Record<TaskStatus, KanbanTask[]>>(
    (acc, status) => {
      acc[status] = tasks.filter((t) => t.status === status);
      return acc;
    },
    {} as Record<TaskStatus, KanbanTask[]>,
  );

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Kanban 보드</h2>
        <div className="flex items-center gap-2">
          {stats && <StatsStrip stats={stats} />}
          <span className={cn("h-2 w-2 rounded-full", connected ? "bg-seed-success" : "bg-neutral-300")} />
          <span className="text-xs text-muted-foreground">{connected ? "실시간" : "연결 중"}</span>
        </div>
      </div>

      {/* Task columns — stacked vertically to fit a sidebar panel */}
      {tasks.length === 0 ? (
        <p className="text-xs text-muted-foreground">작업이 없습니다.</p>
      ) : (
        <div className="space-y-4">
          {STATUS_ORDER.map((status) => (
            <Column key={status} status={status} tasks={grouped[status]} />
          ))}
        </div>
      )}
    </div>
  );
}
