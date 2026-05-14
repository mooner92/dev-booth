import { SessionDetailClient } from "@/components/SessionDetailClient";

export const dynamic = "force-static";
export const dynamicParams = false;

// `output: "export"` requires a non-empty list. We emit a single placeholder
// page; the FastAPI host (or any static server) is configured to serve this
// HTML for any unknown `/session/<name>/` path. The client component reads
// the real session name from `window.location.pathname`, so the page works
// for any session at runtime without server-side rendering.
export function generateStaticParams() {
  return [{ name: "_" }];
}

export default function SessionPage() {
  return <SessionDetailClient />;
}
