"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, useState } from "react";
import type { LogEntry } from "@/types";
import { ChatMessage } from "@/components/ChatMessage";
import { SCROLL_ANCHOR_THRESHOLD_PX, CHAT_VIRTUAL_ROW_HEIGHT } from "@/lib/constants";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

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
  const [query, setQuery] = useState("");
  const [stickToBottom, setStickToBottom] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const [activeTab, setActiveTab] = useState<"timeline" | "log">("timeline");

  const activeEntries = activeTab === "timeline" ? timeline : entries;

  const filteredIndices = activeEntries
    .map((e, i) => ({ entry: e, i }))
    .filter(({ entry }) => !query || (entry.body ?? "").toLowerCase().includes(query.toLowerCase()));

  const virtualizer = useVirtualizer({
    count: filteredIndices.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => CHAT_VIRTUAL_ROW_HEIGHT,
    overscan: 8,
  });

  // Sticky autoscroll
  useEffect(() => {
    const el = parentRef.current;
    if (!el || !stickToBottom) return;
    el.scrollTop = el.scrollHeight;
    setUnreadCount(0);
  }, [filteredIndices.length, stickToBottom]);

  useEffect(() => {
    if (!stickToBottom) setUnreadCount((c) => c + 1);
  }, [activeEntries.length, stickToBottom]);

  // Page title notification when tab hidden
  useEffect(() => {
    if (typeof document === "undefined") return;
    function onVis() {
      if (!document.hidden) {
        document.title = "Dev-Booth Dashboard";
      }
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
          <span className="text-xs text-muted-foreground">{filteredIndices.length}건</span>
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
        className="flex-1 overflow-y-auto"
        style={{ position: "relative" }}
      >
        <div style={{ height: `${virtualizer.getTotalSize()}px`, width: "100%", position: "relative" }}>
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const item = filteredIndices[virtualRow.index];
            return (
              <div
                key={virtualRow.key}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                <ChatMessage entry={item.entry} />
              </div>
            );
          })}
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
