"use client";

import { AGENT_COLORS, AGENT_INITIALS, AGENT_LABELS } from "@/lib/constants";

export function AgentAvatar({ agent, size = 28 }: { agent: string; size?: number }) {
  const color = AGENT_COLORS[agent] ?? AGENT_COLORS.system;
  const initials = AGENT_INITIALS[agent] ?? agent.slice(0, 2).toUpperCase();
  const label = AGENT_LABELS[agent] ?? agent;
  return (
    <span
      title={label}
      aria-label={label}
      className="inline-flex shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
      style={{ width: size, height: size, backgroundColor: color }}
    >
      {initials}
    </span>
  );
}
