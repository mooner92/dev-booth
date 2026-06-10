import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AppHeader } from "@/components/AppHeader";
import { SiteFooter } from "@/components/SiteFooter";

// 정보 페이지(소개/사용 안내/FAQ) 공용 셸.
// 상단은 대시보드와 같은 AppHeader를 재사용하고, 본문은 읽기 좋은 폭으로 카드에 담는다.
export function PageShell({
  title,
  intro,
  updated,
  children,
}: {
  title: string;
  intro?: string;
  updated?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          대시보드
        </Link>

        <header className="mt-4">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
          {intro && <p className="mt-2 text-sm leading-6 text-muted-foreground">{intro}</p>}
          {updated && <p className="mt-2 text-xs text-muted-foreground">마지막 수정일 {updated}</p>}
        </header>

        <div className="mt-6 rounded-md border border-border bg-card p-6 shadow-card sm:p-8">
          <div className="space-y-5 text-[15px] leading-7 text-muted-foreground [&_h2:first-child]:mt-0 [&_a]:text-brand [&_a]:underline [&_a]:underline-offset-2 [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:tracking-tight [&_h2]:text-foreground [&_li]:leading-7 [&_ol]:list-decimal [&_ol]:space-y-1.5 [&_ol]:pl-5 [&_strong]:font-semibold [&_strong]:text-foreground [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 hover:[&_a]:text-brand-600">
            {children}
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
