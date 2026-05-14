"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MetricsSnapshot, QueueDepth } from "@/types";
import { QueueDepthCard } from "@/components/QueueDepthCard";
import { MiniChart } from "@/components/MiniChart";

const PRESETS = ["gpu_utilization", "gpu_memory_used", "gpu_temperature", "vllm_requests"];

export function MonitoringPane({ session, queues }: { session: string; queues: Record<string, QueueDepth> }) {
  const [snapshots, setSnapshots] = useState<Record<string, { t: number; v: number }[]>>({});
  const [available, setAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      const results = await Promise.all(PRESETS.map((p) => api.getMetricsPreset(p).catch(() => null)));
      if (cancelled) return;
      const any = results.some((r) => r?.available);
      setAvailable(any);
      const map: Record<string, { t: number; v: number }[]> = { ...snapshots };
      results.forEach((snap, idx) => {
        if (!snap || !snap.available) return;
        const preset = PRESETS[idx];
        const point = Object.values(snap.series)[0]?.points[0];
        if (!point) return;
        const arr = map[preset] ?? [];
        arr.push({ t: point[0], v: point[1] });
        map[preset] = arr.slice(-30);
      });
      setSnapshots(map);
    }
    tick();
    const id = window.setInterval(tick, 5000);
    return () => { cancelled = true; window.clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  return (
    <div className="space-y-3 overflow-y-auto p-4">
      <QueueDepthCard queues={queues} />
      {available === false && (
        <div className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
          Prometheus 메트릭을 사용할 수 없습니다.
        </div>
      )}
      <MiniChart title="GPU 사용률 (%)" data={snapshots.gpu_utilization ?? []} unit="%" />
      <MiniChart title="GPU 메모리" data={snapshots.gpu_memory_used ?? []} color="#0070F3" unit=" MiB" />
      <MiniChart title="GPU 온도 (°C)" data={snapshots.gpu_temperature ?? []} color="#00B493" unit="°C" />
      <MiniChart title="vLLM 처리/초" data={snapshots.vllm_requests ?? []} color="#FF4136" />
    </div>
  );
}
