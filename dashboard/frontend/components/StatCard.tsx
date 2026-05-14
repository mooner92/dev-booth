"use client";

import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  hint?: string;
  tone?: "neutral" | "success" | "warning" | "error" | "brand";
}) {
  const toneClass = {
    neutral: "text-foreground",
    success: "text-seed-success",
    warning: "text-seed-warning",
    error: "text-seed-error",
    brand: "text-brand",
  }[tone];
  return (
    <div className="rounded-md border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <Icon className={cn("h-4 w-4", toneClass)} />
      </div>
      <div className={cn("mt-2 text-2xl font-semibold", toneClass)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}
