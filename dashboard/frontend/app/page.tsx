"use client";

import { useEffect, useState } from "react";
import { Activity, Cpu, GitCommit, Server, Search, Plus, X, Github } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AppHeader } from "@/components/AppHeader";
import { StatCard } from "@/components/StatCard";
import { SessionCard } from "@/components/SessionCard";
import { SessionCardSkeleton } from "@/components/SessionCardSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { NewSessionModal } from "@/components/NewSessionModal";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { GithubStatus, SessionSummary, StatusSnapshot } from "@/types";

export default function Page() {
  const router = useRouter();

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [statuses, setStatuses] = useState<Record<string, StatusSnapshot>>({});
  const [vllmOk, setVllmOk] = useState<boolean | undefined>(undefined);

  // Search + filter state
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "done" | "unknown">("all");

  // GitHub bot account status
  const [githubStatus, setGithubStatus] = useState<GithubStatus | null>(null);

  // New session modal
  const [newSessionOpen, setNewSessionOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadOnce() {
      try {
        const list = await api.listSessions();
        if (cancelled) return;
        setSessions(list);
        // fetch status for each in parallel (best-effort)
        const detail = await Promise.allSettled(list.map((s) => api.getStatus(s.name)));
        if (cancelled) return;
        const map: Record<string, StatusSnapshot> = {};
        detail.forEach((r, idx) => {
          if (r.status === "fulfilled") map[list[idx].name] = r.value;
        });
        setStatuses(map);
      } catch (err) {
        if (err instanceof ApiError) {
          toast.error(`세션 목록을 가져오지 못했습니다 (${err.status})`);
        } else {
          toast.error("백엔드에 연결할 수 없습니다");
        }
        setSessions([]);
      }
    }
    async function loadMetrics() {
      try {
        const snap = await api.getMetricsPreset("vllm_requests");
        if (cancelled) return;
        setVllmOk(snap.available);
      } catch {
        if (!cancelled) setVllmOk(false);
      }
    }
    // Fetch GitHub bot status once on mount — best-effort, ignore errors
    async function loadGithubStatus() {
      try {
        const status = await api.getGithubStatus();
        if (!cancelled) setGithubStatus(status);
      } catch {
        // Silently ignore — backend may not have this endpoint yet
      }
    }
    loadOnce();
    loadMetrics();
    loadGithubStatus();
    const id = window.setInterval(loadOnce, 5000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, []);

  const activeCount = sessions
    ? sessions.filter((s) => statuses[s.name]?.state === "running").length
    : 0;

  // Filter logic.
  // Note: StatusSnapshot.state uses "idle" as the closest proxy for "완료" —
  // there is no explicit "done" state in the backend model.
  const filteredSessions = (sessions ?? []).filter((s) => {
    const status = statuses[s.name]?.state;
    const matchSearch =
      !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      (s.agents ?? []).join(" ").toLowerCase().includes(search.toLowerCase());
    const matchStatus =
      statusFilter === "all" ||
      (statusFilter === "running" && status === "running") ||
      (statusFilter === "done" && status === "idle") ||
      (statusFilter === "unknown" && (!status || status === "unknown"));
    return matchSearch && matchStatus;
  });

  return (
    <main>
      <AppHeader activeSessions={activeCount} vllmOk={vllmOk} />
      <div className="mx-auto max-w-7xl px-6 py-8">
        {/* Page title + New Session button */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">세션 대시보드</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              AI 에이전트 세션의 12단계 진행 상황과 큐 상태를 한 곳에서 봅니다.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setNewSessionOpen(true)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
          >
            <Plus className="h-4 w-4" />
            새 작업 시작
          </button>
        </div>

        {/* Stats row — 4 cards including GitHub bot account */}
        <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={Activity} label="활성 세션" value={activeCount} tone="brand" />
          <StatCard icon={Server} label="전체 세션" value={sessions?.length ?? "—"} />
          <StatCard
            icon={Cpu}
            label="vLLM 상태"
            value={vllmOk === undefined ? "확인 중" : vllmOk ? "온라인" : "오프라인"}
            tone={vllmOk ? "success" : "neutral"}
          />
          <StatCard
            icon={Github}
            label="GitHub 봇 계정"
            value={githubStatus?.account ?? "—"}
            hint={
              githubStatus?.logged_in
                ? `→ ${githubStatus.target} PR 대상`
                : "연결 안됨"
            }
          />
        </section>

        {/* Session list */}
        <section className="mt-8">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">세션 목록</h2>

          {/* Search + status filter row */}
          <div className="mb-6 mt-4 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[200px] max-w-sm flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="세션명 또는 에이전트로 검색..."
                className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-brand"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label="검색 지우기"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <div className="flex gap-1">
              {(["all", "running", "done", "unknown"] as const).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setStatusFilter(f)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-xs transition-colors",
                    statusFilter === f
                      ? "border-brand bg-brand text-white"
                      : "border-border bg-card text-muted-foreground hover:border-muted-foreground",
                  )}
                >
                  {f === "all"
                    ? "전체"
                    : f === "running"
                    ? "실행 중"
                    : f === "done"
                    ? "완료"
                    : "미상"}
                </button>
              ))}
            </div>
            <span className="ml-auto text-xs text-muted-foreground">
              {sessions === null ? "로딩 중..." : `${filteredSessions.length}개 세션`}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions === null &&
              Array.from({ length: 3 }).map((_, i) => <SessionCardSkeleton key={i} />)}
            {sessions !== null && filteredSessions.length === 0 && (
              <div className="sm:col-span-2 lg:col-span-3">
                <EmptyState
                  title={
                    search || statusFilter !== "all"
                      ? "검색 결과가 없습니다"
                      : "아직 실행 중인 세션이 없습니다"
                  }
                  hint={
                    search || statusFilter !== "all"
                      ? "다른 검색어나 필터를 사용해 보세요."
                      : "Dev-Booth가 새 세션을 시작하면 여기에 표시됩니다."
                  }
                />
              </div>
            )}
            {sessions !== null &&
              filteredSessions.map((s) => (
                <SessionCard key={s.name} session={s} status={statuses[s.name]} />
              ))}
          </div>
        </section>
      </div>

      {/* New session modal */}
      <NewSessionModal
        open={newSessionOpen}
        onClose={() => setNewSessionOpen(false)}
        onCreated={(name) => {
          setNewSessionOpen(false);
          router.push(`/session/${encodeURIComponent(name)}`);
        }}
      />
    </main>
  );
}
