"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Search } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { SessionSocket } from "@/lib/ws";
import { ChatStream } from "@/components/ChatStream";
import { MonacoModal } from "@/components/MonacoModal";
import { KanbanBoard, trimTaskTitle } from "@/components/KanbanBoard";
import { useKanban } from "@/hooks/useKanban";
import type { LogEntry, SessionDetail, StatusSnapshot, WSMessage } from "@/types";
import { STAGE_LABELS, STAGE_ORDER } from "@/lib/constants";

// ── Helpers ───────────────────────────────────────────────────────────────────

function toBoardSlug(name: string): string {
  return name.toLowerCase().replace(/[_ ]+/g, "-");
}

function readSessionNameFromUrl(): string {
  if (typeof window === "undefined") return "";
  const match = window.location.pathname.match(/\/session\/([^/]+)/);
  if (!match) return "";
  const raw = decodeURIComponent(match[1]);
  return raw === "_" ? "" : raw;
}

// ── Shell (name resolution) ───────────────────────────────────────────────────

export function SessionDetailClient({ name: propName }: { name?: string } = {}) {
  const [name, setName] = useState<string>(propName ?? "");
  useEffect(() => {
    if (!propName) {
      setName(readSessionNameFromUrl());
    }
  }, [propName]);

  if (!name) {
    return (
      <main className="grid h-screen place-items-center">
        <div className="text-sm text-muted-foreground">세션 이름을 확인 중…</div>
      </main>
    );
  }
  return <SessionDetailInner name={name} />;
}

// ── Inner ─────────────────────────────────────────────────────────────────────

function SessionDetailInner({ name }: { name: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [status, setStatus] = useState<StatusSnapshot | null>(null);
  // JSONL-driven fallback entries (pre-kanban sessions)
  const [jsonlEntries, setJsonlEntries] = useState<LogEntry[]>([]);
  const [viewPath, setViewPath] = useState<string | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [wsState, setWsState] = useState<"connecting" | "open" | "closed" | "reconnecting">(
    "connecting",
  );
  const [searchOpen, setSearchOpen] = useState(false);
  // Selected task for kanban chat feed (null = fall back to JSONL stream)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const socketRef = useRef<SessionSocket | null>(null);

  const boardSlug = toBoardSlug(name);
  const { tasks, logsByTask, timeline } = useKanban(boardSlug, selectedTaskId ?? undefined);
  const selectedTaskTitle = selectedTaskId
    ? tasks.find((t) => t.id === selectedTaskId)?.title
    : undefined;

  // Auto-select the first running task when tasks load, if nothing selected yet
  useEffect(() => {
    if (selectedTaskId !== null) return;
    const running = tasks.find((t) => t.status === "running");
    if (running) setSelectedTaskId(running.id);
  }, [tasks, selectedTaskId]);

  // Resolve the entries to show in ChatStream:
  // - If a task is selected AND that task has kanban logs → show kanban logs
  // - Otherwise fall back to JSONL stream (pre-kanban sessions still work)
  const activeTaskLogs = selectedTaskId ? (logsByTask[selectedTaskId] ?? null) : null;
  const chatEntries: LogEntry[] =
    activeTaskLogs && activeTaskLogs.length > 0 ? activeTaskLogs : jsonlEntries;

  // ── Derived progress values ──────────────────────────────────────────────────
  const { progressPercent, currentStageName } = useMemo(() => {
    const total = tasks.length;
    if (total === 0) {
      // Fall back to status.current_stage if no kanban tasks yet
      const stageIdx = status?.current_stage ?? 0;
      const stageId = status?.current_stage_id ?? STAGE_ORDER[stageIdx] ?? "";
      return {
        progressPercent: total === 0 ? Math.round((stageIdx / STAGE_ORDER.length) * 100) : 0,
        currentStageName: STAGE_LABELS[stageId] ?? stageId,
      };
    }
    const done = tasks.filter((t) => t.status === "done").length;
    const pct = Math.round((done / total) * 100);
    const running = tasks.find((t) => t.status === "running");
    const stageName = running
      ? trimTaskTitle(running.title)
      : done === total
        ? "완료"
        : "대기 중";
    return { progressPercent: pct, currentStageName: stageName };
  }, [tasks, status]);

  // ── Data load ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const [d, logs] = await Promise.all([
          api.getSession(name),
          api.getLogs(name, { limit: 200 }),
        ]);
        setDetail(d);
        setStatus(d.status);
        setJsonlEntries(logs.entries);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          toast.error("세션을 찾을 수 없습니다");
          router.push("/");
        } else {
          toast.error("세션 데이터를 불러오지 못했습니다");
        }
      }
    }
    load();
  }, [name, router]);

  // ── WebSocket ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_WS_BASE ?? "";
    const sock = new SessionSocket(name, { baseUrl: wsBase });
    socketRef.current = sock;
    const offState = sock.onState((s) => setWsState(s));
    const off = sock.on((msg: WSMessage) => {
      if (msg.type === "log") {
        setJsonlEntries((prev) => [...prev, msg.entry]);
      } else if (msg.type === "status") {
        setStatus(msg.status);
      } else if (msg.type === "reset") {
        toast.info(`로그 회전 감지 — 재로드 (${msg.reason})`);
        api
          .getLogs(name, { limit: 200 })
          .then((p) => setJsonlEntries(p.entries))
          .catch(() => {});
      }
    });
    sock.connect();
    return () => {
      off();
      offState();
      sock.close();
    };
  }, [name]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────────
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      } else if (e.key === "Escape") {
        if (viewerOpen) setViewerOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewerOpen]);

  // ── Render ────────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* LEFT: kanban sidebar 240px */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border lg:flex">
        {/* Sidebar header: back nav + session name */}
        <div className="shrink-0 border-b border-border px-3 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => router.push("/")}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              aria-label="목록으로"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> 목록
            </button>
            <span className="ml-1 truncate text-sm font-semibold" title={name}>
              {name}
            </span>
          </div>
          {detail && (
            <p
              className="mt-0.5 truncate text-[10px] text-muted-foreground"
              title={detail.root}
            >
              {detail.root}
            </p>
          )}
        </div>

        {/* Kanban task list + GPU footer */}
        <div className="min-h-0 flex-1 overflow-hidden">
          <KanbanBoard
            boardSlug={boardSlug}
            selectedTaskId={selectedTaskId ?? undefined}
            onTaskSelect={setSelectedTaskId}
          />
        </div>
      </aside>

      {/* RIGHT: main content */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top bar: progress + controls */}
        <div className="shrink-0 border-b border-border bg-card px-4 py-2">
          <div className="flex items-center justify-between gap-3">
            <span
              className="truncate text-xs text-muted-foreground"
              title={currentStageName}
            >
              {currentStageName}
            </span>
            <div className="flex shrink-0 items-center gap-3">
              <span className="text-[10px] text-muted-foreground">
                WS:{" "}
                {wsState === "open"
                  ? "연결됨"
                  : wsState === "reconnecting"
                    ? "재연결 중"
                    : wsState === "closed"
                      ? "끊김"
                      : "연결 중"}
              </span>
              <button
                type="button"
                onClick={() => setSearchOpen((v) => !v)}
                className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[10px] hover:bg-muted"
                title="검색 (⌘F)"
              >
                <Search className="h-3 w-3" /> 검색
              </button>
            </div>
          </div>
          {/* Progress bar */}
          <div className="mt-1.5 flex items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground">
              {progressPercent}%
            </span>
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-brand transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Chat stream — full remaining height */}
        <div className="min-h-0 flex-1 overflow-hidden">
          <ChatStream
            entries={chatEntries}
            timeline={timeline}
            selectedTaskId={selectedTaskId ?? undefined}
            selectedTaskTitle={selectedTaskTitle}
            searchOpen={searchOpen}
            onCloseSearch={() => setSearchOpen(false)}
          />
        </div>
      </main>

      {/* Monaco file viewer (still reachable programmatically) */}
      <MonacoModal
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        session={name}
        path={viewPath}
      />
    </div>
  );
}
