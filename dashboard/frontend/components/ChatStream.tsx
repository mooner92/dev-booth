"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, useState } from "react";
import type { LogEntry } from "@/types";
import { ChatMessage } from "@/components/ChatMessage";
import { SCROLL_ANCHOR_THRESHOLD_PX, CHAT_VIRTUAL_ROW_HEIGHT } from "@/lib/constants";
import { Search } from "lucide-react";

export function ChatStream({
  entries,
  searchOpen,
  onCloseSearch,
}: {
  entries: LogEntry[];
  searchOpen: boolean;
  onCloseSearch: () => void;
}) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [stickToBottom, setStickToBottom] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);

  const filteredIndices = entries
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
  }, [entries.length, stickToBottom]);

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

  return (
    <div className="flex h-full flex-col">
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
