"use client";

import Link from "next/link";
import type { SessionSummary, StatusSnapshot } from "@/types";
import { StageBar } from "@/components/StageBar";
import { AGENT_COLORS, AGENT_LABELS, SESSION_STATE_LABELS } from "@/lib/constants";
import { formatDistanceToNowStrict, parseISO } from "date-fns";
import { ko } from "date-fns/locale";
import { GitBranch, Circle } from "lucide-react";

export function SessionCard({ session, status }: { session: SessionSummary; status?: StatusSnapshot }) {
  const stage = status?.current_stage ?? 0;
  const state = status?.state ?? "unknown";
  const lastActive = status?.last_active_at ?? session.last_modified;
  const stateLabel = SESSION_STATE_LABELS[state] ?? state;
  const stateColor = state === "running" ? "bg-seed-success" : state === "idle" ? "bg-neutral-400" : state === "error" ? "bg-seed-error" : "bg-neutral-300";
  const currentAgent = status?.current_agent;
  return (
    <Link
      href={`/session/${encodeURIComponent(session.name)}`}
      className="block rounded-md border border-border bg-card p-5 shadow-card transition-shadow hover:shadow-cardHover"
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="text-base font-semibold text-foreground">{session.name}</div>
          <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <GitBranch className="h-3 w-3" />
            <span className="truncate">{session.root}</span>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs">
          <span className={`inline-block h-2 w-2 rounded-full ${stateColor}`} />
          {stateLabel}
        </span>
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
        {currentAgent && (
          <span className="inline-flex items-center gap-1">
            <Circle className="h-2 w-2 fill-current" style={{ color: AGENT_COLORS[currentAgent] ?? "#6B7280" }} />
            {AGENT_LABELS[currentAgent] ?? currentAgent}
          </span>
        )}
        {lastActive && (
          <span>
            · {formatDistanceToNowStrict(parseISO(lastActive), { addSuffix: true, locale: ko })}
          </span>
        )}
      </div>

      <div className="mt-4">
        <StageBar stage={stage} />
      </div>
    </Link>
  );
}
