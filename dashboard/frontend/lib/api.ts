import type {
  FileContent,
  FileTree,
  LogPage,
  MetricsSnapshot,
  QueueDepth,
  SessionDetail,
  SessionSummary,
  StatusSnapshot,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function apiGet<T>(path: string): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let body: unknown = undefined;
    try { body = await res.json(); } catch {}
    throw new ApiError(res.status, `API ${path} returned ${res.status}`, body);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => apiGet<{ ok: boolean; version: string; sessions_root: string }>("/api/health"),
  listSessions: () => apiGet<SessionSummary[]>("/api/sessions"),
  getSession: (name: string) => apiGet<SessionDetail>(`/api/sessions/${encodeURIComponent(name)}`),
  getStatus: (name: string) => apiGet<StatusSnapshot>(`/api/sessions/${encodeURIComponent(name)}/status`),
  getQueues: (name: string) => apiGet<Record<string, QueueDepth>>(`/api/sessions/${encodeURIComponent(name)}/queues`),
  getLogs: (name: string, opts?: { after?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.after) params.set("after", opts.after);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return apiGet<LogPage>(`/api/sessions/${encodeURIComponent(name)}/logs${qs ? `?${qs}` : ""}`);
  },
  getFiles: (name: string) => apiGet<FileTree>(`/api/sessions/${encodeURIComponent(name)}/files`),
  readFile: (name: string, path: string) =>
    apiGet<FileContent>(`/api/sessions/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`),
  getMetricsPreset: (preset: string) => apiGet<MetricsSnapshot>(`/api/metrics/preset/${encodeURIComponent(preset)}`),
};
