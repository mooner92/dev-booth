"use client";

import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Layers, Github } from "lucide-react";
import { siteConfig } from "@/lib/siteConfig";

export function AppHeader({ activeSessions, vllmOk }: { activeSessions?: number; vllmOk?: boolean }) {
  return (
    <header className="sticky top-0 z-40 h-16 border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-brand text-white">
            <Layers className="h-4 w-4" />
          </span>
          <span className="text-lg font-semibold text-foreground">Dev-Booth</span>
          {activeSessions !== undefined && (
            <span className="ml-3 rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">
              활성 세션 {activeSessions}
            </span>
          )}
        </Link>
        <div className="flex items-center gap-3">
          <Link
            href="/guide"
            className="hidden text-xs text-muted-foreground transition-colors hover:text-foreground sm:inline"
          >
            사용 안내
          </Link>
          <Link
            href="/village"
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            🏢 Village
          </Link>
          <a
            href={siteConfig.githubUrl}
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub 저장소"
            title="GitHub 저장소"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Github className="h-4 w-4" />
          </a>
          <span className={`inline-flex items-center gap-2 text-xs ${vllmOk ? "text-seed-success" : "text-neutral-400"}`}>
            <span className={`inline-block h-2 w-2 rounded-full ${vllmOk ? "bg-seed-success" : "bg-neutral-400"}`} />
            vLLM
          </span>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
