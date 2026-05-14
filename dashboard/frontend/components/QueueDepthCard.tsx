"use client";

import type { QueueDepth } from "@/types";
import { AGENT_COLORS, AGENT_LABELS, AGENTS } from "@/lib/constants";

export function QueueDepthCard({ queues }: { queues: Record<string, QueueDepth> }) {
  return (
    <div className="rounded-md border border-border bg-card p-4 shadow-card">
      <h3 className="text-sm font-semibold text-foreground">AWG 큐 상태</h3>
      <ul className="mt-3 space-y-3">
        {AGENTS.map((agent) => {
          const q = queues[agent] ?? { inbox: 0, processing: 0, processed: 0, dead: 0 };
          return (
            <li key={agent} className="text-xs">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: AGENT_COLORS[agent] }} />
                  <span className="font-medium text-foreground">{AGENT_LABELS[agent]}</span>
                </span>
                <span className="text-muted-foreground">inbox {q.inbox} · proc {q.processing}</span>
              </div>
              <div className="mt-1 flex gap-1 text-[10px] text-muted-foreground">
                <span>processed {q.processed}</span>
                <span>dead {q.dead}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
