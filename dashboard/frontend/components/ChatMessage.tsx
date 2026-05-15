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
import { useMemo, useState } from "react";

function processBody(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw;
  // Best-effort unicode unescape: `\uXXXX` → real char, but don't break already-rendered text.
  // If the body looks like it contains '\u' sequences, try JSON.parse on a quoted form;
  // on parse failure, keep the original.
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
  const relative = useMemo(() => {
    if (!ts) return "";
    try {
      return formatDistanceToNowStrict(parseISO(ts), { addSuffix: true, locale: ko });
    } catch {
      return ts;
    }
  }, [ts]);
  const [showAbsolute, setShowAbsolute] = useState(false);
  const isComment = entry.kind === "comment";
  const rawBody = entry.body ?? "";
  const isToolCall =
    entry.kind === "tool" ||
    rawBody.startsWith("kanban_") ||
    rawBody.includes("preparing ");
  const body = processBody(rawBody);

  return (
    <div
      className={cn(
        "flex items-start gap-3 px-4 py-2.5",
        isComment && "bg-muted/30",
        isToolCall && !isComment && "bg-muted/40",
      )}
    >
      <AgentAvatar agent={agent} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold" style={{ color }}>{label}</span>
          {isComment && entry.task_title && (
            <span className="ml-2 rounded bg-card border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {entry.task_title}
            </span>
          )}
          {entry.to && (
            <span className="text-xs text-muted-foreground">→ {AGENT_LABELS[entry.to] ?? entry.to}</span>
          )}
          {entry.kind && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{entry.kind}</span>
          )}
          <button
            type="button"
            className="ml-auto text-[11px] text-muted-foreground hover:text-foreground"
            onClick={() => setShowAbsolute((v) => !v)}
            title={ts}
          >
            {showAbsolute ? ts : relative}
          </button>
        </div>
        <div className="prose prose-sm dark:prose-invert mt-1 max-w-none break-words text-foreground">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {body}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
