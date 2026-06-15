"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { LogEntry } from "@/types";
import { ChatMessage } from "@/components/ChatMessage";
import { SCROLL_ANCHOR_THRESHOLD_PX } from "@/lib/constants";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

// Patterns Hermes injects around tool calls / frame markers — they have no
// reader value on the log tab. Timeline (kanban_comment + status_change) is
// intentional 1:1 narration and gets no filtering.
const NOISE_BODY_PATTERNS: RegExp[] = [
  /^Hermes$/i,
  /^tools>$/,
  /^_response>$/,
  /^<\/?tool_response>$/,
  /^<\/?output>$/,
  /^markdown>$/,
  /^\s*$/,
];

const GROUP_WINDOW_MS = 5_000;

function isNoise(body: string): boolean {
  return NOISE_BODY_PATTERNS.some((p) => p.test(body.trim()));
}

export type DisplayEntry = LogEntry & { repeat?: number; lastAt?: string };

/** Collapse consecutive identical messages (same from + kind + body) into a
 * single row carrying a repeat count + the latest timestamp. A stuck worker
 * re-emits the exact same kanban_comment dozens of times (non-termination
 * loop); collapsing keeps the timeline readable without losing the signal
 * that it repeated. */
function collapseDuplicates(entries: LogEntry[]): DisplayEntry[] {
  const out: DisplayEntry[] = [];
  for (const e of entries) {
    const body = (e.body ?? "").trim();
    const prev = out[out.length - 1];
    if (
      prev &&
      body &&
      (prev.body ?? "").trim() === body &&
      prev.from === e.from &&
      prev.kind === e.kind
    ) {
      prev.repeat = (prev.repeat ?? 1) + 1;
      prev.lastAt = e.createdAt ?? prev.lastAt;
      continue;
    }
    out.push({ ...e });
  }
  return out;
}

/** Merge consecutive same-agent text entries within GROUP_WINDOW_MS into a
 * single entry with their bodies joined by a single space. tool/comment/
 * status_change entries are never merged — only kind in {undefined, null,
 * "text"} qualifies. */
function groupAndFilterEntries(entries: LogEntry[]): LogEntry[] {
  const out: LogEntry[] = [];
  for (const e of entries) {
    const body = (e.body ?? "").trim();
    if (isNoise(body)) continue;

    const isPlainText = !e.kind || e.kind === "text";
    const last = out[out.length - 1];
    const lastIsPlainText = last && (!last.kind || last.kind === "text");
    const lastBody = (last?.body ?? "").trim();

    if (
      last &&
      isPlainText &&
      lastIsPlainText &&
      last.from === e.from &&
      Math.abs(
        new Date(e.createdAt ?? 0).getTime() -
          new Date(last.createdAt ?? 0).getTime(),
      ) < GROUP_WINDOW_MS
    ) {
      out[out.length - 1] = {
        ...last,
        body: lastBody ? `${lastBody} ${body}` : body,
      };
      continue;
    }
    out.push({ ...e, body });
  }
  return out;
}

// v10: dropped @tanstack/react-virtual in favor of a plain flex-column map.
// The WS payload caps timelines at 100 entries and per-task logs at 50, so
// the worst-case render is a few hundred rows — well under the threshold
// where virtualization is worth the layout cost. The old fixed-height
// virtualizer clipped long messages and created overlapping rows; the new
// natural-height map renders each ChatMessage at its real height.

export function ChatStream({
  entries,
  timeline,
  selectedTaskId,
  selectedTaskTitle,
  searchOpen,
  onCloseSearch,
}: {
  entries: LogEntry[];
  timeline: LogEntry[];
  selectedTaskId?: string;
  selectedTaskTitle?: string;
  searchOpen: boolean;
  onCloseSearch: () => void;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [stickToBottom, setStickToBottom] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const [activeTab, setActiveTab] = useState<"timeline" | "log">("timeline");

  // Timeline stays raw (kanban_comment + status_change are intentional 1:1
  // narration); only the log tab gets grouping + noise filtering.
  const rawEntries = activeTab === "timeline" ? timeline : entries;
  const activeEntries = useMemo(
    () =>
      collapseDuplicates(
        activeTab === "log" ? groupAndFilterEntries(rawEntries) : rawEntries,
      ),
    [activeTab, rawEntries],
  );
  const q = query.toLowerCase();
  const filtered = q
    ? activeEntries.filter((e) => (e.body ?? "").toLowerCase().includes(q))
    : activeEntries;

  // Sticky autoscroll — scroll the bottom anchor into view whenever the
  // filtered list grows AND the user is following the bottom.
  useEffect(() => {
    if (!stickToBottom) return;
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
    setUnreadCount(0);
  }, [filtered.length, stickToBottom]);

  // When NOT following the bottom and new messages arrive, bump unread.
  useEffect(() => {
    if (!stickToBottom) setUnreadCount((c) => c + 1);
  }, [activeEntries.length, stickToBottom]);

  // Page title notification when tab hidden.
  useEffect(() => {
    if (typeof document === "undefined") return;
    function onVis() {
      if (!document.hidden) document.title = "Dev-Booth Dashboard";
    }
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (document.hidden && entries.length > 0) {
      document.title = `(${entries.length}) Dev-Booth Dashboard`;
    }
  }, [entries.length]);

  function onScroll() {
    const el = parentRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
    setStickToBottom(distanceFromBottom < SCROLL_ANCHOR_THRESHOLD_PX);
    if (distanceFromBottom < SCROLL_ANCHOR_THRESHOLD_PX) setUnreadCount(0);
  }

  const logTabLabel = selectedTaskTitle
    ? `태스크 로그 ${selectedTaskTitle.slice(0, 20)}`
    : "태스크 로그";

  return (
    <div className="flex h-full flex-col">
      {/* Tab header strip */}
      <div className="flex shrink-0 border-b border-border">
        <button
          type="button"
          onClick={() => setActiveTab("timeline")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors",
            activeTab === "timeline"
              ? "border-brand text-brand"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          팀 타임라인
          {timeline.length > 0 && (
            <span className="ml-1.5 rounded-full bg-brand/15 px-1.5 py-0.5 text-[10px] font-semibold text-brand">
              {timeline.length}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("log")}
          className={cn(
            "px-4 py-2 text-sm font-medium border-b-2 transition-colors",
            activeTab === "log"
              ? "border-brand text-brand"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {selectedTaskId ? (
            logTabLabel
          ) : (
            <span>
              태스크 로그{" "}
              <span className="text-muted-foreground/60">(태스크 선택)</span>
            </span>
          )}
        </button>
      </div>

      {searchOpen && (
        <div className="flex items-center gap-2 border-b border-border bg-card px-3 py-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") onCloseSearch(); }}
            placeholder="로그 검색 (Esc로 닫기)"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <span className="text-xs text-muted-foreground">{filtered.length}건</span>
        </div>
      )}

      {/* Empty states */}
      {activeTab === "timeline" && timeline.length === 0 && (
        <div className="px-4 py-6 text-xs text-muted-foreground">
          에이전트 간 대화가 없습니다. kanban_comment() 호출 시 여기에 표시됩니다.
        </div>
      )}
      {activeTab === "log" && !selectedTaskId && (
        <div className="px-4 py-6 text-xs text-muted-foreground">
          오른쪽 칸반 보드에서 태스크를 클릭하세요.
        </div>
      )}

      <div
        ref={parentRef}
        onScroll={onScroll}
        className="relative min-h-0 flex-1 overflow-y-auto"
      >
        <div className="flex flex-col py-2">
          {filtered.map((entry, i) => (
            <ChatMessage
              key={entry.id ?? `${activeTab}-${i}`}
              entry={entry}
            />
          ))}
          <div ref={bottomRef} />
        </div>
        {!stickToBottom && unreadCount > 0 && (
          <button
            type="button"
            onClick={() => {
              setStickToBottom(true);
              setUnreadCount(0);
            }}
            className="sticky bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-brand px-3 py-1.5 text-xs font-medium text-white shadow"
          >
            새 메시지 {unreadCount}개 ↓
          </button>
        )}
      </div>
    </div>
  );
}
