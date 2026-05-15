"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { WS_RECONNECT_BACKOFF_MS } from "@/lib/constants";
import type { LogEntry } from "@/types";

// ── Types mirroring the backend contract ─────────────────────────────────────

export type TaskStatus =
  | "triage"
  | "todo"
  | "ready"
  | "running"
  | "blocked"
  | "done"
  | "archived";

export interface KanbanTask {
  id: string;
  title: string;
  body?: string | null;
  assignee?: string | null;
  status: TaskStatus;
  priority?: number | null;
  workspace_kind?: string | null;
  created_at?: number | null;
  started_at?: number | null;
  completed_at?: number | null;
  result?: string | null;
}

export interface KanbanComment {
  id: string;
  task_id: string;
  author: string;
  body: string;
  created_at?: number | null;
}

export interface KanbanStats {
  triage: number;
  todo: number;
  ready: number;
  running: number;
  blocked: number;
  done: number;
}

export type KanbanConnectionState = "open" | "connecting" | "closed";

export interface UseKanbanResult {
  tasks: KanbanTask[];
  comments: KanbanComment[];
  stats: KanbanStats | null;
  /** @deprecated use connectionState instead */
  connected: boolean;
  connectionState: KanbanConnectionState;
  /** per-task log entries merged from WS kanban_update pushes and optional REST prefetch */
  logsByTask: Record<string, LogEntry[]>;
}

// ── Helper ────────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} returned ${res.status}`);
  return res.json() as Promise<T>;
}

function kanbanWsUrl(boardSlug: string): string {
  if (typeof window === "undefined") {
    return `/api/kanban/ws/kanban/${encodeURIComponent(boardSlug)}`;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/kanban/ws/kanban/${encodeURIComponent(boardSlug)}`;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useKanban(
  boardSlug: string,
  selectedTaskId?: string,
): UseKanbanResult {
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [comments, setComments] = useState<KanbanComment[]>([]);
  const [stats, setStats] = useState<KanbanStats | null>(null);
  const [connectionState, setConnectionState] = useState<KanbanConnectionState>("connecting");
  const [logsByTask, setLogsByTask] = useState<Record<string, LogEntry[]>>({});

  const alive = useRef(true);
  const attempt = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initial REST load — tasks + stats; logs come via next WS push.
  // If selectedTaskId is provided, also prefetch that task's log immediately.
  useEffect(() => {
    if (!boardSlug) return;
    let cancelled = false;
    const fetches: [
      Promise<{ tasks: KanbanTask[] }>,
      Promise<KanbanStats>,
      Promise<{ messages: LogEntry[]; runs: unknown[] } | null>,
    ] = [
      apiFetch<{ tasks: KanbanTask[] }>(`/api/kanban/boards/${encodeURIComponent(boardSlug)}/tasks`),
      apiFetch<KanbanStats>(`/api/kanban/boards/${encodeURIComponent(boardSlug)}/stats`),
      selectedTaskId
        ? apiFetch<{ messages: LogEntry[]; runs: unknown[] }>(
            `/api/kanban/boards/${encodeURIComponent(boardSlug)}/tasks/${encodeURIComponent(selectedTaskId)}/log`,
          ).catch(() => null) // REST log prefetch is best-effort
        : Promise.resolve(null),
    ];
    Promise.all(fetches)
      .then(([taskRes, statsRes, logRes]) => {
        if (cancelled) return;
        setTasks(taskRes.tasks);
        setStats(statsRes);
        if (logRes && selectedTaskId) {
          setLogsByTask((prev) => ({
            ...prev,
            [selectedTaskId]: logRes.messages ?? [],
          }));
        }
      })
      .catch((err) => {
        if (!cancelled) console.error("[useKanban] REST prefetch failed:", err);
      });
    return () => { cancelled = true; };
  }, [boardSlug, selectedTaskId]);

  // WebSocket with exponential-backoff reconnect
  const openWs = useCallback(() => {
    if (!alive.current || !boardSlug) return;

    const ws = new WebSocket(kanbanWsUrl(boardSlug));
    wsRef.current = ws;

    ws.onopen = () => {
      attempt.current = 0;
      setConnectionState("open");
    };

    ws.onmessage = (evt) => {
      let msg: {
        type: string;
        tasks?: KanbanTask[];
        comments?: KanbanComment[];
        logs?: Record<string, LogEntry[]>;
      };
      try { msg = JSON.parse(evt.data as string); } catch { return; }
      if (msg.type === "kanban_update") {
        if (msg.tasks) setTasks(msg.tasks);
        if (msg.comments) setComments(msg.comments);
        if (msg.logs) {
          // 새 로그를 기존 맵에 머지 (WS payload가 완전한 최신 스냅샷이므로 덮어쓰기)
          setLogsByTask((prev) => ({ ...prev, ...msg.logs }));
        }
      }
    };

    ws.onclose = () => {
      setConnectionState("closed");
      if (!alive.current) return;
      const backoff = WS_RECONNECT_BACKOFF_MS[
        Math.min(attempt.current, WS_RECONNECT_BACKOFF_MS.length - 1)
      ];
      attempt.current += 1;
      const jitter = Math.random() * 0.2 * backoff;
      timerRef.current = setTimeout(openWs, backoff + jitter);
    };

    ws.onerror = () => {
      // close handler will trigger retry
    };
  }, [boardSlug]);

  useEffect(() => {
    if (!boardSlug) return;
    alive.current = true;
    attempt.current = 0;
    setConnectionState("connecting");
    openWs();
    return () => {
      alive.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close(1000, "unmount");
      wsRef.current = null;
    };
  }, [boardSlug, openWs]);

  return {
    tasks,
    comments,
    stats,
    connected: connectionState === "open",
    connectionState,
    logsByTask,
  };
}
