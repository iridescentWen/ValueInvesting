"use client";

import { useT } from "@/lib/i18n";
import type { FinancialSnapshot, Market } from "@/lib/api";
import { fmtMoney, fmtPeriodYear } from "@/lib/fmt";

export function FinancialsTable({
  snapshots,
  market,
}: {
  snapshots: FinancialSnapshot[];
  market: Market;
}) {
  const t = useT();
  if (snapshots.length === 0) {
    return (
      <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
        {t("pages.stock.financials_empty")}
      </div>
    );
  }
  return (
    <div className="rounded-lg border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/50 text-left text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">
              {t("pages.stock.cols.period")}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {t("pages.stock.cols.revenue")}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {t("pages.stock.cols.net_income")}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {t("pages.stock.cols.total_assets")}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {t("pages.stock.cols.total_equity")}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {t("pages.stock.cols.operating_cashflow")}
            </th>
            <th className="px-4 py-3 text-right font-medium">
              {t("pages.stock.cols.capex")}
            </th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((s) => (
            <tr key={s.period} className="border-b last:border-b-0 hover:bg-muted/30">
              <td className="px-4 py-3 font-mono font-medium">
                {fmtPeriodYear(s.period)}
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {fmtMoney(s.revenue, market)}
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {fmtMoney(s.net_income, market)}
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {fmtMoney(s.total_assets, market)}
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {fmtMoney(s.total_equity, market)}
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {fmtMoney(s.operating_cashflow, market)}
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {fmtMoney(s.capex, market)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
