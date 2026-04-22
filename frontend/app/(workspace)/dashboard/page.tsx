"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useT } from "@/lib/i18n";
import {
  fetchScreener,
  fetchScreenerStatus,
  type ScreenerPrewarmStatus,
  type ScreenerRow,
} from "@/lib/api";
import { fmtMarketCap, fmtNum, fmtPct } from "@/lib/fmt";
import { useAppStore, type Market } from "@/lib/store";

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

function interpolate(tpl: string, vars: Record<string, string | number>): string {
  return tpl.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
}

const STATUS_POLL_MS = 2000;

export default function DashboardPage() {
  const t = useT();
  const router = useRouter();
  const market = useAppStore((s) => s.market);
  // rows 按市场分桶存——切换市场时直接展示上一份对应的缓存,避免 "A 股数据显示
  // 成港股" 的错位
  const [rowsByMarket, setRowsByMarket] = useState<
    Partial<Record<Market, ScreenerRow[]>>
  >({});
  const [updatedByMarket, setUpdatedByMarket] = useState<
    Partial<Record<Market, Date>>
  >({});
  const [progressByMarket, setProgressByMarket] = useState<
    Partial<Record<Market, ScreenerPrewarmStatus>>
  >({});
  const [error, setError] = useState<string | null>(null);
  // 每次 load 单调递增,用于丢弃过期请求
  const reqIdRef = useRef(0);
  // 当前在跑的 status 轮询 interval id;切市场 / ready / 失败都清掉
  const pollRef = useRef<number | null>(null);

  const rows = rowsByMarket[market] ?? [];
  const lastUpdated = updatedByMarket[market] ?? null;
  const progress = progressByMarket[market] ?? null;
  const hasData = rows.length > 0;
  const warming = progress?.status === "warming" || progress?.status === "idle";

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadRows = useCallback(
    async (targetMarket: Market, reqId: number): Promise<boolean> => {
      // 真正拉 rows——仅在 status=ready 时调用。返回 true 表示取到了数据。
      const resp = await fetchScreener(targetMarket, 20, false);
      if (reqId !== reqIdRef.current) return false;
      if (resp.kind === "ready") {
        setRowsByMarket((prev) => ({ ...prev, [targetMarket]: resp.rows }));
        setUpdatedByMarket((prev) => ({ ...prev, [targetMarket]: new Date() }));
        setProgressByMarket((prev) => ({
          ...prev,
          [targetMarket]: { status: "ready", done: 0, total: 0, started_at: null, error: null },
        }));
        return true;
      }
      setProgressByMarket((prev) => ({ ...prev, [targetMarket]: resp.progress }));
      return false;
    },
    [],
  );

  const startPolling = useCallback(
    (targetMarket: Market, reqId: number) => {
      stopPolling();
      const tick = async () => {
        if (reqId !== reqIdRef.current) {
          stopPolling();
          return;
        }
        try {
          const statuses = await fetchScreenerStatus();
          const mine = statuses[targetMarket];
          if (reqId !== reqIdRef.current) return;
          setProgressByMarket((prev) => ({ ...prev, [targetMarket]: mine }));
          if (mine.status === "ready") {
            stopPolling();
            await loadRows(targetMarket, reqId);
          } else if (mine.status === "failed") {
            stopPolling();
            setError(mine.error ?? "prewarm failed");
          }
        } catch (e) {
          // 状态接口抖一下不算致命,继续轮询
          console.warn("screener status poll failed", e);
        }
      };
      pollRef.current = window.setInterval(tick, STATUS_POLL_MS);
      // 立即触发一次,不用等 2s
      void tick();
    },
    [loadRows, stopPolling],
  );

  const load = useCallback(
    async (targetMarket: Market, refresh: boolean) => {
      const myReqId = ++reqIdRef.current;
      setError(null);
      stopPolling();
      try {
        const resp = await fetchScreener(targetMarket, 20, refresh);
        if (myReqId !== reqIdRef.current) return;
        if (resp.kind === "ready") {
          setRowsByMarket((prev) => ({ ...prev, [targetMarket]: resp.rows }));
          setUpdatedByMarket((prev) => ({ ...prev, [targetMarket]: new Date() }));
          setProgressByMarket((prev) => ({
            ...prev,
            [targetMarket]: {
              status: "ready",
              done: 0,
              total: 0,
              started_at: null,
              error: null,
            },
          }));
          return;
        }
        // warming:展示进度 + 轮询
        setProgressByMarket((prev) => ({ ...prev, [targetMarket]: resp.progress }));
        startPolling(targetMarket, myReqId);
      } catch (e: unknown) {
        if (myReqId !== reqIdRef.current) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [startPolling, stopPolling],
  );

  useEffect(() => {
    void load(market, false);
    return stopPolling;
  }, [market, load, stopPolling]);

  // 组件卸载时也清定时器(上面的 cleanup 每次 market change 已经跑,这层保险)
  useEffect(() => {
    return stopPolling;
  }, [stopPolling]);

  const onRefresh = () => {
    void load(market, true);
  };

  const warmingHint = (() => {
    if (!progress) return null;
    if (progress.status === "failed") {
      return (
        t("dashboard.warming_failed_prefix") + (progress.error ?? "unknown")
      );
    }
    if (progress.total > 0) {
      const pct = Math.floor((progress.done / progress.total) * 100);
      return interpolate(t("dashboard.warming_hint"), {
        done: progress.done,
        total: progress.total,
        pct,
      });
    }
    return t("dashboard.warming_hint_indeterminate");
  })();

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
            <Button variant="outline" size="sm" onClick={onRefresh}>
              {warming ? t("dashboard.refreshing") : t("dashboard.refresh")}
            </Button>
            <span className="text-xs text-muted-foreground">
              {t("dashboard.last_updated")}:{" "}
              {fmtRelative(lastUpdated, t("dashboard.never_updated"))}
            </span>
          </div>
        </div>

        {/* warming 时把进度条挂在表格上方,不管有没有已有数据都显示;refresh
            期间如果上一份数据还在 rowsByMarket,继续显示成 60% 透明度 */}
        {warming && progress && (
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{warmingHint}</span>
              {progress.total > 0 && (
                <span className="font-mono">
                  {Math.floor((progress.done / progress.total) * 100)}%
                </span>
              )}
            </div>
            {progress.total > 0 && (
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border/50">
                <div
                  className="h-full bg-primary transition-all duration-500 ease-out"
                  style={{
                    width: `${Math.floor((progress.done / progress.total) * 100)}%`,
                  }}
                />
              </div>
            )}
          </div>
        )}

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
                {warming && !hasData && (
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
                      onClick={(e) => {
                        const url = `/stock/${encodeURIComponent(r.symbol)}?market=${market}`;
                        // cmd/ctrl/middle-click → 新标签;否则同标签跳转
                        if (e.metaKey || e.ctrlKey) {
                          window.open(url, "_blank");
                        } else {
                          router.push(url);
                        }
                      }}
                      className={`cursor-pointer border-b last:border-b-0 hover:bg-muted/50 ${
                        warming ? "opacity-60 transition-opacity" : ""
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
                {!warming && !hasData && (
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
