import type { WSMessage } from "@/types";
import { WS_RECONNECT_BACKOFF_MS } from "@/lib/constants";

type Listener = (msg: WSMessage) => void;
type StateListener = (state: "connecting" | "open" | "closed" | "reconnecting") => void;

export interface SessionSocketOptions {
  baseUrl?: string;  // e.g. "ws://localhost:7001" or "" for same-origin
  resumeFrom?: string | null;
}

export class SessionSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private stateListeners = new Set<StateListener>();
  private lastSeq: string | null = null;
  private attempt = 0;
  private alive = true;
  private heartbeatTimer: number | null = null;

  constructor(public session: string, private options: SessionSocketOptions = {}) {
    this.lastSeq = options.resumeFrom ?? null;
  }

  connect(): void {
    this.alive = true;
    this.attempt = 0;
    this.open();
  }

  close(): void {
    this.alive = false;
    if (this.heartbeatTimer) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    this.ws?.close(1000, "client close");
    this.ws = null;
    this.emitState("closed");
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onState(listener: StateListener): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  private url(): string {
    const base = this.options.baseUrl ?? "";
    if (base) {
      return `${base}/ws/${encodeURIComponent(this.session)}`;
    }
    // same-origin
    if (typeof window === "undefined") {
      return `/ws/${encodeURIComponent(this.session)}`;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/${encodeURIComponent(this.session)}`;
  }

  private emit(msg: WSMessage) {
    for (const l of this.listeners) {
      try { l(msg); } catch (err) { console.error("WS listener error", err); }
    }
  }

  private emitState(state: "connecting" | "open" | "closed" | "reconnecting") {
    for (const l of this.stateListeners) {
      try { l(state); } catch (err) { console.error("WS state listener error", err); }
    }
  }

  private open() {
    if (!this.alive) return;
    this.emitState(this.attempt === 0 ? "connecting" : "reconnecting");
    const ws = new WebSocket(this.url());
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.emitState("open");
      ws.send(JSON.stringify({ type: "subscribe", resume_from: this.lastSeq }));
      if (this.heartbeatTimer) window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, 15000);
    };

    ws.onmessage = (evt) => {
      let msg: WSMessage;
      try { msg = JSON.parse(evt.data); } catch { return; }
      if (msg.type === "log" && msg.seq) {
        this.lastSeq = msg.seq;
      } else if (msg.type === "reset") {
        this.lastSeq = null;
      }
      this.emit(msg);
    };

    ws.onclose = () => {
      if (this.heartbeatTimer) {
        window.clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = null;
      }
      if (!this.alive) return;
      const delay = WS_RECONNECT_BACKOFF_MS[Math.min(this.attempt, WS_RECONNECT_BACKOFF_MS.length - 1)];
      this.attempt += 1;
      const jitter = Math.random() * 0.2 * delay;
      this.emitState("reconnecting");
      window.setTimeout(() => this.open(), delay + jitter);
    };

    ws.onerror = () => {
      // close handler will retry
    };
  }
}
