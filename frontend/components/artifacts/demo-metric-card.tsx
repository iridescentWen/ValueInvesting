import { TrendingDownIcon, TrendingUpIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export function DemoMetricCard({
  data,
}: {
  data: { label: string; value: string; delta?: number };
}) {
  const up = (data.delta ?? 0) >= 0;
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="text-xs text-muted-foreground">{data.label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold tabular">
        {data.value}
      </div>
      {data.delta !== undefined && (
        <div
          className={cn(
            "mt-1 flex items-center gap-1 font-mono text-xs tabular",
            up ? "text-(color:--color-up)" : "text-(color:--color-down)"
          )}
        >
          {up ? (
            <TrendingUpIcon className="size-3" />
          ) : (
            <TrendingDownIcon className="size-3" />
          )}
          {up ? "+" : ""}
          {data.delta.toFixed(2)}%
        </div>
      )}
    </div>
  );
}
