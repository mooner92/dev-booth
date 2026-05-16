"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// ── Types (mirror dashboard/backend/services/village_status.py) ─────────────
interface AgentState {
  state: string;
  task: string;
  task_status: string;
  area: string;
  emoji: string;
  label: string;
  x: number;
  y: number;
}

interface VillageState {
  board: string;
  progress: number;
  done: number;
  total: number;
  agents: Record<string, AgentState>;
}

// ── Theme tokens ─────────────────────────────────────────────────────────────
const AGENT_COLORS: Record<string, string> = {
  conductor: "#FF4136",
  architect: "#0070F3",
  executor:  "#00B493",
};

const OFFICE_AREAS = {
  desk_conductor: { x: 340, y: 80,  w: 140, h: 100, label: "Conductor Desk" },
  desk_architect: { x: 80,  y: 240, w: 140, h: 100, label: "Architect Desk" },
  desk_executor:  { x: 580, y: 240, w: 140, h: 100, label: "Executor Desk" },
  meeting:        { x: 300, y: 250, w: 200, h: 120, label: "Meeting" },
  breakroom:      { x: 80,  y: 380, w: 640, h: 80,  label: "Break Room" },
} as const;

const CANVAS_W = 800;
const CANVAS_H = 500;

// ── Helpers ──────────────────────────────────────────────────────────────────
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

function villageWsUrl(boardSlug: string): string {
  if (typeof window === "undefined") {
    return `/api/village/ws/${encodeURIComponent(boardSlug)}`;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/village/ws/${encodeURIComponent(boardSlug)}`;
}

function getAgentPosition(agentName: string, state: AgentState): { x: number; y: number } {
  if (state.area === "desk") {
    const key = `desk_${agentName}` as keyof typeof OFFICE_AREAS;
    const desk = OFFICE_AREAS[key] ?? OFFICE_AREAS.meeting;
    return { x: desk.x + desk.w / 2, y: desk.y + desk.h / 2 };
  }
  if (state.area === "hallway") {
    const xs: Record<string, number> = { conductor: 400, architect: 250, executor: 550 };
    return { x: xs[agentName] ?? 400, y: 200 };
  }
  // breakroom + fallback
  const bxs: Record<string, number> = { conductor: 260, architect: 390, executor: 520 };
  return { x: bxs[agentName] ?? 400, y: 415 };
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number,
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawSpeechBubble(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, text: string, color: string,
) {
  const short = text.length > 20 ? text.slice(0, 18) + "…" : text;
  ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
  const tw = Math.min(ctx.measureText(short).width + 16, 180);
  const th = 22;
  const bx = x - tw / 2;
  const by = y - th - 8;

  ctx.fillStyle = color + "dd";
  roundRect(ctx, bx, by, tw, th, 6);
  ctx.fill();

  ctx.fillStyle = "#fff";
  ctx.textAlign = "center";
  ctx.fillText(short, x, by + 15);
}

function drawOffice(ctx: CanvasRenderingContext2D, village: VillageState) {
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H);

  // Background
  ctx.fillStyle = "#1a1a2e";
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

  // Pixel grid
  ctx.strokeStyle = "rgba(255,255,255,0.03)";
  ctx.lineWidth = 1;
  for (let x = 0; x < CANVAS_W; x += 32) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
  }
  for (let y = 0; y < CANVAS_H; y += 32) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
  }

  // Office areas
  const areaColors: Record<string, string> = {
    desk_conductor: "#1e3a5f",
    desk_architect: "#1e3a5f",
    desk_executor:  "#1e3a5f",
    meeting:        "#1a3a2a",
    breakroom:      "#2a1a1a",
  };
  for (const [key, area] of Object.entries(OFFICE_AREAS)) {
    ctx.fillStyle = areaColors[key] ?? "#222";
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 2;
    roundRect(ctx, area.x, area.y, area.w, area.h, 8);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textAlign = "center";
    ctx.fillText(area.label, area.x + area.w / 2, area.y + 16);
  }

  // Agents
  for (const [name, agent] of Object.entries(village.agents)) {
    const pos = getAgentPosition(name, agent);
    const color = AGENT_COLORS[name] ?? "#888";
    const isRunning = agent.task_status === "running";

    if (isRunning) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 24 + Math.sin(Date.now() / 300) * 4, 0, Math.PI * 2);
      ctx.fillStyle = color + "30";
      ctx.fill();
    }

    ctx.beginPath();
    ctx.arc(pos.x, pos.y, 20, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();

    ctx.font = "18px serif";
    ctx.textAlign = "center";
    ctx.fillText(agent.emoji, pos.x, pos.y + 6);

    ctx.fillStyle = "#fff";
    ctx.font = "bold 11px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.fillText(agent.label, pos.x, pos.y + 38);

    if (agent.task && isRunning) {
      drawSpeechBubble(ctx, pos.x, pos.y - 30, agent.task, color);
    }
  }
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function VillagePage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const wsRef = useRef<WebSocket | null>(null);

  const [village, setVillage] = useState<VillageState | null>(null);
  const [boards, setBoards] = useState<string[]>([]);
  const [selectedBoard, setSelectedBoard] = useState<string>("");
  const [connected, setConnected] = useState(false);

  // Board list (one-shot)
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/village/boards`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d: { boards?: string[] }) => {
        if (cancelled) return;
        const list = d.boards ?? [];
        setBoards(list);
        if (list.length > 0) setSelectedBoard((prev) => prev || list[0]);
      })
      .catch((err) => console.warn("[village] boards fetch failed:", err));
    return () => { cancelled = true; };
  }, []);

  // WebSocket lifecycle
  useEffect(() => {
    if (!selectedBoard) return;

    // Prime via REST so the page paints something before the first WS push.
    fetch(`${API_BASE}/api/village/boards/${encodeURIComponent(selectedBoard)}/state`, {
      cache: "no-store",
    })
      .then((r) => r.json())
      .then((d: VillageState) => setVillage(d))
      .catch((err) => console.warn("[village] state fetch failed:", err));

    const ws = new WebSocket(villageWsUrl(selectedBoard));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data as string) as VillageState & { type?: string };
        if (data.type === "village_update") {
          setVillage({
            board: data.board,
            progress: data.progress,
            done: data.done,
            total: data.total,
            agents: data.agents,
          });
        }
      } catch { /* ignore malformed payload */ }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [selectedBoard]);

  // Canvas render loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let stopped = false;
    function loop() {
      if (stopped) return;
      if (village && ctx) drawOffice(ctx, village);
      animRef.current = requestAnimationFrame(loop);
    }
    animRef.current = requestAnimationFrame(loop);
    return () => {
      stopped = true;
      cancelAnimationFrame(animRef.current);
    };
  }, [village]);

  return (
    <main className="min-h-screen bg-[#0f0f1a] text-white">
      <div className="mx-auto flex max-w-5xl flex-col items-center px-4 py-8">
        {/* Header */}
        <div className="mb-6 w-full">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="font-mono text-xl font-bold text-white">
                🏢 Dev-Booth Village
              </h1>
              <p className="mt-1 text-xs text-white/40">
                에이전트들의 실시간 작업 현황
              </p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={selectedBoard}
                onChange={(e) => setSelectedBoard(e.target.value)}
                className="rounded-lg border border-white/20 bg-white/10 px-3 py-1.5 text-xs text-white outline-none focus:border-white/40"
              >
                {boards.length === 0 && <option value="">— no boards —</option>}
                {boards.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    connected ? "animate-pulse bg-green-400" : "bg-red-400",
                  )}
                />
                <span className="text-xs text-white/40">
                  {connected ? "실시간" : "연결 중"}
                </span>
              </div>
              <a
                href="/"
                className="text-xs text-white/40 transition-colors hover:text-white/80"
              >
                ← 대시보드
              </a>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        {village && (
          <div className="mb-4 w-full">
            <div className="mb-1 flex items-center justify-between">
              <span className="font-mono text-xs text-white/40">전체 진행률</span>
              <span className="font-mono text-xs text-white/60">
                {village.done} / {village.total} 태스크 완료 ({village.progress}%)
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-orange-500 transition-all duration-500"
                style={{ width: `${village.progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Canvas */}
        <div className="w-full overflow-hidden rounded-xl border border-white/10 shadow-2xl">
          <canvas
            ref={canvasRef}
            width={CANVAS_W}
            height={CANVAS_H}
            className="h-auto w-full"
            style={{ imageRendering: "pixelated" }}
          />
        </div>

        {/* Agent cards */}
        {village && (
          <div className="mt-6 grid w-full grid-cols-1 gap-4 sm:grid-cols-3">
            {Object.entries(village.agents).map(([name, agent]) => (
              <div
                key={name}
                className={cn(
                  "space-y-2 rounded-xl border p-4 transition-all",
                  agent.task_status === "running"
                    ? "border-orange-500/40 bg-orange-500/5"
                    : agent.task_status === "blocked"
                      ? "border-amber-500/40 bg-amber-500/5"
                      : "border-white/10 bg-white/5",
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: AGENT_COLORS[name] ?? "#888" }}
                  />
                  <span className="font-mono text-sm font-bold text-white">
                    {agent.label}
                  </span>
                  <span className="ml-auto text-lg">{agent.emoji}</span>
                </div>
                <div
                  className={cn(
                    "w-fit rounded-full px-2 py-0.5 font-mono text-xs",
                    agent.task_status === "running" && "bg-green-500/20 text-green-400",
                    agent.task_status === "blocked" && "bg-amber-500/20 text-amber-400",
                    agent.task_status === "done"    && "bg-blue-500/20 text-blue-400",
                    (agent.task_status === "idle" || agent.task_status === "todo" ||
                      agent.task_status === "ready" || agent.task_status === "triage") &&
                      "bg-white/10 text-white/40",
                  )}
                >
                  {agent.task_status === "running" ? "● 작업 중" :
                   agent.task_status === "blocked" ? "⊘ 차단됨" :
                   agent.task_status === "done"    ? "✓ 완료" :
                   agent.task_status === "ready"   ? "↻ 대기열" :
                   "○ 대기"}
                </div>
                {agent.task && (
                  <p className="line-clamp-2 font-mono text-xs text-white/60">
                    {agent.task}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {boards.length === 0 && (
          <div className="py-20 text-center">
            <p className="mb-4 text-4xl">🏢</p>
            <p className="font-mono text-sm text-white/40">
              활성 보드가 없습니다.
            </p>
            <p className="mt-1 text-xs text-white/20">
              대시보드에서 새 작업을 시작하세요.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
