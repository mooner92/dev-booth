"use client";

import { STAGE_LABELS, STAGE_ORDER } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function StageBar({ stage }: { stage: number }) {
  const pct = Math.max(0, Math.min(12, stage)) / 12 * 100;
  const label = STAGE_ORDER[Math.max(0, stage - 1)] ? STAGE_LABELS[STAGE_ORDER[stage - 1]] : "대기 중";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{stage > 0 ? `${stage}/12 · ${label}` : "단계 미감지"}</span>
        <span className="text-muted-foreground">{Math.round(pct)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            stage === 12 ? "bg-seed-success" : "bg-brand",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
