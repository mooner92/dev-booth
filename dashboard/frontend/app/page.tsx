"use client";

import { useEffect, useState } from "react";
import { Activity, Cpu, GitCommit, Server } from "lucide-react";
import { toast } from "sonner";
import { AppHeader } from "@/components/AppHeader";
import { StatCard } from "@/components/StatCard";
import { SessionCard } from "@/components/SessionCard";
import { SessionCardSkeleton } from "@/components/SessionCardSkeleton";
import { EmptyState } from "@/components/EmptyState";
import { api, ApiError } from "@/lib/api";
import type { SessionSummary, StatusSnapshot } from "@/types";

export default function Page() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [statuses, setStatuses] = useState<Record<string, StatusSnapshot>>({});
  const [vllmOk, setVllmOk] = useState<boolean | undefined>(undefined);

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
    loadOnce();
    loadMetrics();
    const id = window.setInterval(loadOnce, 5000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, []);

  const activeCount = sessions ? sessions.filter((s) => statuses[s.name]?.state === "running").length : 0;

  return (
    <main>
      <AppHeader activeSessions={activeCount} vllmOk={vllmOk} />
      <div className="mx-auto max-w-7xl px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">세션 대시보드</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          AI 에이전트 세션의 12단계 진행 상황과 큐 상태를 한 곳에서 봅니다.
        </p>

        <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard icon={Activity} label="활성 세션" value={activeCount} tone="brand" />
          <StatCard icon={Server} label="전체 세션" value={sessions?.length ?? "—"} />
          <StatCard
            icon={Cpu}
            label="vLLM 상태"
            value={vllmOk === undefined ? "확인 중" : vllmOk ? "온라인" : "오프라인"}
            tone={vllmOk ? "success" : "neutral"}
          />
          <StatCard icon={GitCommit} label="오늘 커밋" value="—" hint="orchestrator 연동 후 표시" />
        </section>

        <section className="mt-8">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">세션 목록</h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions === null && Array.from({ length: 3 }).map((_, i) => <SessionCardSkeleton key={i} />)}
            {sessions !== null && sessions.length === 0 && (
              <div className="sm:col-span-2 lg:col-span-3">
                <EmptyState />
              </div>
            )}
            {sessions !== null && sessions.map((s) => (
              <SessionCard key={s.name} session={s} status={statuses[s.name]} />
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
