// Mirrors backend Pydantic models (services/models.py).

export interface LogEntry {
  id?: string | null;
  kind?: string | null;
  from?: string | null;
  to?: string | null;
  body?: string | null;
  refs?: Record<string, unknown> | null;
  priority?: number | null;
  createdAt?: string | null;
  createdAtMs?: number | null;
}

export interface LogPage {
  session: string;
  entries: LogEntry[];
  next_after?: string | null;
  has_more: boolean;
  total_lines_estimate?: number | null;
}

export interface QueueDepth {
  inbox: number;
  processing: number;
  processed: number;
  dead: number;
}

export interface StatusSnapshot {
  session: string;
  state: "running" | "idle" | "error" | "unknown";
  current_stage: number;
  current_stage_id?: string | null;
  current_agent?: string | null;
  last_active_at?: string | null;
  queues: Record<string, QueueDepth>;
  test_results?: Record<string, number> | null;
}

export interface SessionSummary {
  name: string;
  root: string;
  has_log: boolean;
  has_queues: boolean;
  agents: string[];
  last_modified?: string | null;
}

export interface SessionDetail extends SessionSummary {
  status: StatusSnapshot;
  repo_url?: string | null;
  repo_name?: string | null;
  branch?: string | null;
  started_at?: string | null;
}

export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number | null;
  modified_at?: string | null;
  children?: FileNode[] | null;
}

export interface FileTree {
  session: string;
  root: FileNode;
  truncated: boolean;
}

export interface FileContent {
  session: string;
  path: string;
  size: number;
  binary: boolean;
  truncated: boolean;
  content?: string | null;
  mime?: string | null;
}

export interface MetricSeries {
  label: string;
  points: [number, number][];
}

export interface MetricsSnapshot {
  available: boolean;
  fetched_at: string;
  series: Record<string, MetricSeries>;
  error?: string | null;
}

export type WSMessage =
  | { type: "hello"; session: string; version: string; server_time: string }
  | { type: "log"; ts: string; seq: string; entry: LogEntry }
  | { type: "status"; ts: string; status: StatusSnapshot }
  | { type: "typing"; ts: string; agent: string; state: "start" | "end" }
  | { type: "file_changed"; ts: string; path: string; change: "added" | "modified" | "deleted" }
  | { type: "metrics"; ts: string; snapshot: MetricsSnapshot }
  | { type: "heartbeat"; ts: string }
  | { type: "reset"; ts: string; reason: string; seq: string }
  | { type: "pong"; ts: string }
  | { type: "error"; ts: string; error: string };
