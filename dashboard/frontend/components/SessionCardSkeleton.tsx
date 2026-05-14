export function SessionCardSkeleton() {
  return (
    <div className="rounded-md border border-border bg-card p-5">
      <div className="h-5 w-32 animate-pulse rounded bg-muted" />
      <div className="mt-2 h-3 w-48 animate-pulse rounded bg-muted" />
      <div className="mt-6 h-2 w-full animate-pulse rounded-full bg-muted" />
    </div>
  );
}
