import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";

export default async function StockDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  return (
    <WorkspacePlaceholder
      title={`个股 · ${ticker}`}
      description="主图（TradingView lightweight-charts）· 关键指标 · 估值卡 · 年报摘录。Phase 2 接入。"
    />
  );
}
