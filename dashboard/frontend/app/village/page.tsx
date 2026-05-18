"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

// Same-origin proxy path. The dashboard backend (village_proxy router)
// forwards everything under this prefix to http://localhost:19000 and
// rewrites Star-Office-UI's absolute paths so all assets/APIs route back
// through the proxy. This works from LAN and Cloudflare alike without
// needing port 19000 reachable from the browser.
const STAR_OFFICE_PROXY_PATH = "/api/village-iframe/";

function resolveStarOfficeOrigin(): string {
  if (typeof window === "undefined") return "";
  return STAR_OFFICE_PROXY_PATH;
}

export default function VillagePage() {
  const [boards, setBoards] = useState<string[]>([]);
  const [selectedBoard, setSelectedBoard] = useState<string>("");
  // Initial origin is empty so SSR renders no iframe. Without this guard, the
  // server-side iframe pointed at https://village.excusa.uk — which sits
  // behind Cloudflare Access (X-Frame-Options: DENY) and showed a refused-to-
  // load error before the client effect could swap to the LAN URL.
  const [origin, setOrigin] = useState<string>("");
  const [iframeStatus, setIframeStatus] = useState<"loading" | "ok" | "error">("loading");

  useEffect(() => {
    setOrigin(resolveStarOfficeOrigin());
  }, []);

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

  return (
    <main className="flex h-screen flex-col bg-[#0f0f1a] text-white">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-2">
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="text-xs text-white/40 transition-colors hover:text-white/80"
          >
            ← 대시보드
          </a>
          <h1 className="font-mono text-sm font-bold text-white">
            🏢 Dev-Booth Village
          </h1>
          <span className="font-mono text-[10px] text-white/30">
            powered by Star-Office-UI
          </span>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selectedBoard}
            onChange={(e) => setSelectedBoard(e.target.value)}
            className="rounded border border-white/20 bg-white/10 px-2 py-1 text-xs text-white outline-none focus:border-white/40"
            aria-label="Active kanban board"
          >
            {boards.length === 0 && <option value="">— no boards —</option>}
            {boards.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
          {origin && (
            <a
              href={origin}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-white/40 transition-colors hover:text-white/80"
            >
              ↗ open
            </a>
          )}
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              iframeStatus === "ok"
                ? "animate-pulse bg-green-400"
                : iframeStatus === "error"
                  ? "bg-red-400"
                  : "bg-amber-400",
            )}
            title={iframeStatus}
          />
        </div>
      </header>

      <div className="relative flex-1">
        {origin ? (
          <iframe
            key={origin}
            src={origin}
            title="Dev-Booth Village (Star-Office-UI)"
            className="absolute inset-0 h-full w-full border-none"
            onLoad={() => setIframeStatus("ok")}
            onError={() => setIframeStatus("error")}
          />
        ) : null}
        {(!origin || iframeStatus === "loading") && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-white/40">
            {origin ? `loading ${origin}…` : "resolving Village host…"}
          </div>
        )}
      </div>
    </main>
  );
}
