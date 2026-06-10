import { ChevronDown } from "lucide-react";

export type FaqItem = { q: string; a: React.ReactNode };

// native <details> 기반 아코디언 — 정적 export에서 JS 없이 동작한다.
export function FaqAccordion({ items }: { items: FaqItem[] }) {
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <details
          key={i}
          className="group rounded-md border border-border bg-card transition-colors open:border-brand/40"
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-[15px] font-medium text-foreground marker:hidden [&::-webkit-details-marker]:hidden">
            <span className="inline-flex items-center gap-2">
              <span className="text-brand">Q.</span>
              {item.q}
            </span>
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <div className="px-4 pb-4 pt-0 text-[15px] leading-7 text-muted-foreground [&_a]:text-brand [&_a]:underline [&_a]:underline-offset-2 [&_strong]:font-semibold [&_strong]:text-foreground">
            {item.a}
          </div>
        </details>
      ))}
    </div>
  );
}
