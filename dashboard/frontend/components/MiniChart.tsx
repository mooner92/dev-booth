"use client";

import { LineChart, Line, ResponsiveContainer, YAxis, Tooltip } from "recharts";

export function MiniChart({
  title,
  data,
  color = "#FF6F0F",
  unit,
}: {
  title: string;
  data: { t: number; v: number }[];
  color?: string;
  unit?: string;
}) {
  const last = data.length ? data[data.length - 1].v : null;
  return (
    <div className="rounded-md border border-border bg-card p-4 shadow-card">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
        <span className="text-sm font-semibold" style={{ color }}>
          {last !== null ? `${last.toFixed(1)}${unit ?? ""}` : "—"}
        </span>
      </div>
      <div className="mt-2 h-12">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip formatter={(value: number) => [`${value.toFixed(2)}${unit ?? ""}`, title]} labelFormatter={() => ""} />
            <Line type="monotone" dataKey="v" stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
