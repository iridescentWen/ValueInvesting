"use client";

import { Badge } from "@/components/ui/badge";
import { useT } from "@/lib/i18n";
import type { Market } from "@/lib/api";

export function StockHeader({
  ticker,
  market,
}: {
  ticker: string;
  market: Market;
}) {
  const t = useT();
  return (
    <div className="flex items-baseline gap-3">
      <h1 className="font-mono text-2xl font-semibold tracking-tight">
        {ticker}
      </h1>
      <Badge variant="outline">{t(`market.${market}` as const)}</Badge>
    </div>
  );
}
