"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/lib/i18n";
import type { Fundamentals, Market } from "@/lib/api";
import { fmtMarketCap, fmtNum, fmtPct } from "@/lib/fmt";

export function FundamentalsCard({
  fundamentals,
  market,
}: {
  fundamentals: Fundamentals | null;
  market: Market;
}) {
  const t = useT();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("pages.stock.fundamentals_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm sm:grid-cols-5">
          <Stat label={t("table.pe")} value={fmtNum(fundamentals?.pe ?? null)} />
          <Stat label={t("table.pb")} value={fmtNum(fundamentals?.pb ?? null)} />
          <Stat label={t("table.roe")} value={fmtPct(fundamentals?.roe ?? null)} />
          <Stat
            label={t("table.dividend_yield")}
            value={fmtPct(fundamentals?.dividend_yield ?? null)}
          />
          <Stat
            label={t("table.market_cap")}
            value={fmtMarketCap(fundamentals?.market_cap ?? null, market)}
          />
        </dl>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="font-mono text-base">{value}</dd>
    </div>
  );
}
