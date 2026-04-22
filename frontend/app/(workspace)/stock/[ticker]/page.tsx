"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  fetchFinancials,
  fetchFundamentals,
  type FinancialSnapshot,
  type Fundamentals,
  type Market,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

import { FinancialsTable } from "./financials-table";
import { FundamentalsCard } from "./fundamentals-card";
import { StockHeader } from "./stock-header";

const MARKETS: readonly Market[] = ["cn", "us", "hk"] as const;

function isMarket(v: string | null): v is Market {
  return v !== null && (MARKETS as readonly string[]).includes(v);
}

export default function StockDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const t = useT();
  const { ticker } = use(params);
  const search = useSearchParams();
  const marketParam = search.get("market");

  if (!isMarket(marketParam)) {
    return <MarketRequiredNotice />;
  }

  return <StockDetailBody ticker={ticker} market={marketParam} />;
}

function StockDetailBody({ ticker, market }: { ticker: string; market: Market }) {
  const t = useT();
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [financials, setFinancials] = useState<FinancialSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetchFundamentals(ticker, market).catch((e: unknown) => {
        throw e instanceof Error ? e : new Error(String(e));
      }),
      fetchFinancials(ticker, market).catch((e: unknown) => {
        throw e instanceof Error ? e : new Error(String(e));
      }),
    ])
      .then(([fund, fins]) => {
        if (cancelled) return;
        setFundamentals(fund);
        setFinancials(fins);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, market]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-8">
      <StockHeader ticker={ticker} market={market} />

      {loading ? (
        <div className="text-sm text-muted-foreground">
          {t("pages.stock.loading")}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {t("pages.stock.error_prefix")}
          {error}
        </div>
      ) : (
        <>
          <FundamentalsCard fundamentals={fundamentals} market={market} />
          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold tracking-tight">
              {t("pages.stock.financials_title")}
            </h2>
            <FinancialsTable snapshots={financials} market={market} />
          </section>
        </>
      )}
    </div>
  );
}

function MarketRequiredNotice() {
  const t = useT();
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-start gap-4 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        {t("pages.stock.market_required_title")}
      </h1>
      <p className="text-sm text-muted-foreground">
        {t("pages.stock.market_required_body")}
      </p>
      <Button asChild variant="outline" size="sm">
        <Link href="/dashboard">{t("pages.stock.back_to_dashboard")}</Link>
      </Button>
    </div>
  );
}
