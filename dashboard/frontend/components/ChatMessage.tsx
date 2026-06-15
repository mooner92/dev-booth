"use client";

import type { LogEntry } from "@/types";
import { AgentAvatar } from "@/components/AgentAvatar";
import { AGENT_COLORS, AGENT_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { formatDistanceToNowStrict, parseISO } from "date-fns";
import { ko } from "date-fns/locale";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { useMemo } from "react";

function processBody(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw;
  // Best-effort unicode unescape: `\uXXXX` → real char, but don't break already-rendered text.
  if (s.includes("\\u")) {
    try {
      const decoded = JSON.parse(`"${s.replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t")}"`);
      if (typeof decoded === "string") s = decoded;
    } catch { /* keep raw on parse failure */ }
  }
  // Strip XML-style framing tags Hermes injects around tool calls.
  s = s.replace(/<\/?tool_response>/g, "").replace(/<\/?output>/g, "");
  return s.replace(/^\s+|\s+$/g, "");
}

export function ChatMessage({ entry }: { entry: LogEntry }) {
  const agent = entry.from ?? "system";
  const color = AGENT_COLORS[agent] ?? AGENT_COLORS.system;
  const label = AGENT_LABELS[agent] ?? agent;
  const ts = entry.createdAt ?? "";

  // Parse once; render an always-visible local clock (HH:MM:SS) plus a hover
  // tooltip with the full local datetime and a relative ("3분 전") hint.
  const date = useMemo(() => {
    if (!ts) return null;
    try { return parseISO(ts); } catch { return null; }
  }, [ts]);
  const clock = date
    ? date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
    : "";
  const relative = useMemo(() => {
    if (!date) return "";
    try { return formatDistanceToNowStrict(date, { addSuffix: true, locale: ko }); } catch { return ""; }
  }, [date]);
  const fullTitle = date ? `${date.toLocaleString("ko-KR")}${relative ? ` · ${relative}` : ""}` : ts;

  const isComment = entry.kind === "comment";
  const isStatusChange = entry.kind === "status_change";
  const rawBody = entry.body ?? "";
  const isDone = isStatusChange && rawBody.startsWith("✅");
  const isBlocked = isStatusChange && rawBody.startsWith("⊘");
  const isToolCall =
    entry.kind === "tool" ||
    rawBody.startsWith("kanban_") ||
    rawBody.includes("preparing ");
  const body = processBody(rawBody);

  return (
    <div
      className={cn(
        "group flex items-start gap-3 border-b border-border/40 px-4 py-3 transition-colors hover:bg-muted/20",
        isComment && "bg-muted/20",
        isDone && "border-l-2 border-l-emerald-500/70 bg-emerald-500/[0.04]",
        isBlocked && "border-l-2 border-l-amber-500/70 bg-amber-500/[0.04]",
      )}
    >
      <AgentAvatar agent={agent} />
      <div className="min-w-0 flex-1">
        {/* Header: agent · task · routing · kind · time */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold leading-none" style={{ color }}>{label}</span>
          {isComment && entry.task_title && (
            <span className="truncate rounded border border-border bg-card px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {entry.task_title}
            </span>
          )}
          {entry.to && (
            <span className="text-xs text-muted-foreground">→ {AGENT_LABELS[entry.to] ?? entry.to}</span>
          )}
          {entry.kind && entry.kind !== "text" && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {entry.kind}
            </span>
          )}
          <time
            title={fullTitle}
            className="ml-auto shrink-0 font-mono text-xs tabular-nums text-muted-foreground/90"
          >
            {clock || "—"}
          </time>
        </div>

        {/* Body: tool calls as a monospace block; prose otherwise */}
        {isToolCall ? (
          <pre className="mt-1.5 overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-border/60 bg-muted/50 px-3 py-2 font-mono text-[13px] leading-relaxed text-foreground/90">
            {body}
          </pre>
        ) : (
          <div className="prose prose-sm dark:prose-invert mt-1 max-w-none break-words text-[15px] leading-relaxed text-foreground [&_p]:my-1">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {body}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
