"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useT } from "@/lib/i18n";
import { fetchScreener, type ScreenerRow } from "@/lib/api";
import { useAppStore, type Market } from "@/lib/store";

function fmtNum(v: string | null, digits = 2): string {
  if (v === null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function fmtPct(v: string | null, digits = 2): string {
  if (v === null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtMarketCap(v: string | null, market: Market): string {
  if (v === null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "—";
  const symbol = market === "us" ? "$" : market === "hk" ? "HK$" : "¥";
  if (n >= 1e12) return `${symbol}${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${symbol}${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${symbol}${(n / 1e6).toFixed(2)}M`;
  return `${symbol}${n.toFixed(0)}`;
}

function fmtRelative(ts: Date | null, neverLabel: string): string {
  if (ts === null) return neverLabel;
  const delta = Date.now() - ts.getTime();
  const sec = Math.floor(delta / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  return `${hr}h`;
}

export default function DashboardPage() {
  const t = useT();
  const market = useAppStore((s) => s.market);
  // rows 按市场分桶存——切换市场时直接展示上一份对应的缓存,避免 "A 股数据显示
  // 成港股" 的错位
  const [rowsByMarket, setRowsByMarket] = useState<
    Partial<Record<Market, ScreenerRow[]>>
  >({});
  const [updatedByMarket, setUpdatedByMarket] = useState<
    Partial<Record<Market, Date>>
  >({});
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqIdRef = useRef(0);

  const rows = rowsByMarket[market] ?? [];
  const lastUpdated = updatedByMarket[market] ?? null;
  const hasData = rows.length > 0;

  const load = useCallback(
    (targetMarket: Market, refresh: boolean) => {
      const myReqId = ++reqIdRef.current;
      setFetching(true);
      setError(null);
      fetchScreener(targetMarket, 20, refresh)
        .then((data) => {
          // 丢弃过期请求结果——市场切换或连点刷新时只认最后一个
          if (myReqId !== reqIdRef.current) return;
          setRowsByMarket((prev) => ({ ...prev, [targetMarket]: data }));
          setUpdatedByMarket((prev) => ({ ...prev, [targetMarket]: new Date() }));
        })
        .catch((e: unknown) => {
          if (myReqId !== reqIdRef.current) return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (myReqId !== reqIdRef.current) return;
          setFetching(false);
        });
    },
    [],
  );

  useEffect(() => {
    load(market, false);
  }, [market, load]);

  const onRefresh = () => load(market, true);

  return (
    <TooltipProvider>
      <div className="mx-auto flex max-w-6xl flex-col gap-6 p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {t(`market.${market}` as const)}
              {t("dashboard.title_suffix")}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {t("dashboard.subtitle")}
            </p>
          </div>
          <div className="flex flex-shrink-0 flex-col items-end gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={onRefresh}
              disabled={fetching}
            >
              {fetching && hasData
                ? t("dashboard.refreshing")
                : t("dashboard.refresh")}
            </Button>
            <span className="text-xs text-muted-foreground">
              {t("dashboard.last_updated")}:{" "}
              {fmtRelative(lastUpdated, t("dashboard.never_updated"))}
            </span>
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {t("dashboard.error_prefix")}
            {error}
          </div>
        ) : (
          <div className="rounded-lg border">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t("table.symbol")}</th>
                  <th className="px-4 py-3 font-medium">{t("table.name")}</th>
                  <th className="px-4 py-3 text-right font-medium">
                    {t("table.pe")}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {t("table.pb")}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {t("table.graham_number")}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {t("table.roe")}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {t("table.dividend_yield")}
                  </th>
                  <th className="px-4 py-3 text-right font-medium">
                    {t("table.market_cap")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {fetching && !hasData && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-10 text-center text-muted-foreground"
                    >
                      <div>{t("dashboard.loading")}</div>
                      <div className="mt-1 text-xs">
                        {t("dashboard.loading_hint")}
                      </div>
                    </td>
                  </tr>
                )}
                {hasData &&
                  rows.map((r) => (
                    <tr
                      key={r.symbol}
                      className={`border-b last:border-b-0 hover:bg-muted/30 ${
                        fetching ? "opacity-60 transition-opacity" : ""
                      }`}
                    >
                      <td className="px-4 py-3 font-mono font-medium">
                        {r.symbol}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {r.name}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {fmtNum(r.pe)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {fmtNum(r.pb)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {fmtNum(r.graham_number)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {r.roe_missing ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="cursor-help border-b border-dashed border-muted-foreground/50 text-muted-foreground">
                                —
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {t("dashboard.roe_missing_tooltip")}
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          fmtPct(r.roe)
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {fmtPct(r.dividend_yield)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono">
                        {fmtMarketCap(r.market_cap, market)}
                      </td>
                    </tr>
                  ))}
                {!fetching && !hasData && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-8 text-center text-muted-foreground"
                    >
                      {t("dashboard.empty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
