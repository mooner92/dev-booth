"use client";

import { Inbox } from "lucide-react";

export function EmptyState({
  title = "아직 실행 중인 세션이 없습니다",
  hint = "Dev-Booth가 새 세션을 시작하면 여기에 표시됩니다.",
}: {
  title?: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-card/50 px-6 py-16 text-center">
      <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand/10 text-brand">
        <Inbox className="h-6 w-6" />
      </span>
      <h3 className="mt-4 text-base font-semibold text-foreground">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
    </div>
  );
}
