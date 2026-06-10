import Link from "next/link";
import { Github, Layers, Mail, ShieldCheck } from "lucide-react";
import { siteConfig, infoNav } from "@/lib/siteConfig";

// 홈/정보 페이지 하단 푸터. (Village는 전체화면 iframe이라 제외)
export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          {/* 브랜드 + 한줄 소개 */}
          <div className="max-w-md">
            <div className="flex items-center gap-2">
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-brand text-white">
                <Layers className="h-4 w-4" />
              </span>
              <span className="text-base font-semibold text-foreground">{siteConfig.name}</span>
            </div>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{siteConfig.description}</p>
            <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-seed-success" />
              모든 추론은 로컬에서 수행 · 코드·데이터 외부 전송 없음
            </p>
            <a
              href={`mailto:${siteConfig.email}`}
              className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <Mail className="h-3.5 w-3.5" />
              문의 {siteConfig.email}
            </a>
          </div>

          {/* 정보 링크 + GitHub */}
          <nav className="flex flex-col gap-2.5 text-sm" aria-label="사이트 정보">
            {infoNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
            <a
              href={siteConfig.githubUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground"
            >
              <Github className="h-4 w-4" />
              GitHub
            </a>
          </nav>
        </div>

        {/* 저작권 */}
        <div className="mt-8 flex flex-col gap-2 border-t border-border pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>
            © {siteConfig.name} · {siteConfig.tagline}
          </p>
          <a
            href={siteConfig.githubUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 transition-colors hover:text-foreground"
          >
            <Github className="h-3.5 w-3.5" />
            {siteConfig.repoLabel}
          </a>
        </div>
      </div>
    </footer>
  );
}
