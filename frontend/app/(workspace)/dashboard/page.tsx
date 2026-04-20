import { fetchFundamentals, fetchStocks, type Fundamentals, type Stock } from "@/lib/api";

type Row = Stock & { fundamentals: Fundamentals | null };

async function loadRows(): Promise<Row[]> {
  const stocks = await fetchStocks("us", 10);
  const rows = await Promise.all(
    stocks.map(async (s): Promise<Row> => {
      try {
        const f = await fetchFundamentals(s.symbol, "us");
        return { ...s, fundamentals: f };
      } catch {
        return { ...s, fundamentals: null };
      }
    }),
  );
  return rows;
}

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

function fmtMarketCap(v: string | null): string {
  if (v === null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(0)}`;
}

export default async function DashboardPage() {
  let rows: Row[] = [];
  let error: string | null = null;
  try {
    rows = await loadRows();
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          美股前 10 支（FMP 数据）·PE/PB/ROE/市值 来自 FMP TTM ratios + profile
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          加载失败：{error}
        </div>
      ) : (
        <div className="rounded-lg border">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Symbol</th>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Exchange</th>
                <th className="px-4 py-3 text-right font-medium">PE (TTM)</th>
                <th className="px-4 py-3 text-right font-medium">PB</th>
                <th className="px-4 py-3 text-right font-medium">ROE</th>
                <th className="px-4 py-3 text-right font-medium">Market Cap</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol} className="border-b last:border-b-0 hover:bg-muted/30">
                  <td className="px-4 py-3 font-mono font-medium">{r.symbol}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{r.exchange ?? "—"}</td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtNum(r.fundamentals?.pe ?? null)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtNum(r.fundamentals?.pb ?? null)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtPct(r.fundamentals?.roe ?? null)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtMarketCap(r.fundamentals?.market_cap ?? null)}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                    无数据
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
