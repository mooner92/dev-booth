"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Search } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { SessionSocket } from "@/lib/ws";
import { AppHeader } from "@/components/AppHeader";
import { FileTreePane } from "@/components/FileTreePane";
import { ChatStream } from "@/components/ChatStream";
import { MonitoringPane } from "@/components/MonitoringPane";
import { MonacoModal } from "@/components/MonacoModal";
import { StageBar } from "@/components/StageBar";
import type { FileTree, LogEntry, SessionDetail, StatusSnapshot, WSMessage } from "@/types";
import { SESSION_STATE_LABELS } from "@/lib/constants";

function readSessionNameFromUrl(): string {
  if (typeof window === "undefined") return "";
  const match = window.location.pathname.match(/\/session\/([^/]+)/);
  if (!match) return "";
  const raw = decodeURIComponent(match[1]);
  return raw === "_" ? "" : raw;
}

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

function SessionDetailInner({ name }: { name: string }) {
  const router = useRouter();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [status, setStatus] = useState<StatusSnapshot | null>(null);
  const [tree, setTree] = useState<FileTree | null>(null);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [viewPath, setViewPath] = useState<string | null>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [wsState, setWsState] = useState<"connecting" | "open" | "closed" | "reconnecting">("connecting");
  const [searchOpen, setSearchOpen] = useState(false);
  const socketRef = useRef<SessionSocket | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [d, t, logs] = await Promise.all([
          api.getSession(name),
          api.getFiles(name),
          api.getLogs(name, { limit: 200 }),
        ]);
        setDetail(d);
        setStatus(d.status);
        setTree(t);
        setEntries(logs.entries);
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

  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_WS_BASE ?? "";
    const sock = new SessionSocket(name, { baseUrl: wsBase });
    socketRef.current = sock;
    const offState = sock.onState((s) => setWsState(s));
    const off = sock.on((msg: WSMessage) => {
      if (msg.type === "log") {
        setEntries((prev) => [...prev, msg.entry]);
      } else if (msg.type === "status") {
        setStatus(msg.status);
      } else if (msg.type === "reset") {
        toast.info(`로그 회전 감지 — 재로드 (${msg.reason})`);
        api.getLogs(name, { limit: 200 }).then((p) => setEntries(p.entries)).catch(() => {});
      }
    });
    sock.connect();
    return () => {
      off();
      offState();
      sock.close();
    };
  }, [name]);

  // Cmd/Ctrl+F to toggle search
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      } else if (e.key === "Escape") {
        if (viewerOpen) {
          setViewerOpen(false);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewerOpen]);

  return (
    <main className="flex h-screen flex-col">
      <AppHeader />
      <div className="flex items-center gap-3 border-b border-border bg-background px-4 py-3">
        <button onClick={() => router.push("/")} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> 목록
        </button>
        <div className="ml-2">
          <h1 className="text-base font-semibold">{name}</h1>
          {detail && <p className="text-xs text-muted-foreground">{detail.root}</p>}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            WS: {wsState === "open" ? "연결됨" : wsState === "reconnecting" ? "재연결 중" : wsState === "closed" ? "끊김" : "연결 중"}
          </span>
          <button
            onClick={() => setSearchOpen((v) => !v)}
            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
          >
            <Search className="h-3 w-3" /> 검색 (⌘F)
          </button>
        </div>
      </div>
      {status && (
        <div className="border-b border-border px-4 py-3">
          <div className="mx-auto max-w-7xl">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 text-sm">
                <span className="font-medium">상태:</span>
                <span>{SESSION_STATE_LABELS[status.state] ?? status.state}</span>
                {status.current_agent && <span className="text-muted-foreground">· {status.current_agent}</span>}
              </div>
              <div className="w-1/2">
                <StageBar stage={status.current_stage} />
              </div>
            </div>
          </div>
        </div>
      )}
      <div className="grid flex-1 overflow-hidden lg:grid-cols-[280px_1fr_320px]">
        <aside className="hidden border-r border-border bg-card lg:block">
          {tree && <FileTreePane root={tree.root} onPick={(p) => { setViewPath(p); setViewerOpen(true); }} />}
        </aside>
        <section className="overflow-hidden">
          <ChatStream entries={entries} searchOpen={searchOpen} onCloseSearch={() => setSearchOpen(false)} />
        </section>
        <aside className="hidden border-l border-border bg-card lg:block">
          <MonitoringPane session={name} queues={status?.queues ?? {}} />
        </aside>
      </div>
      <MonacoModal
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        session={name}
        path={viewPath}
      />
    </main>
  );
}
