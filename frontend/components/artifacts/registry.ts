import type { FC } from "react";
import { DemoMetricCard } from "./demo-metric-card";

/**
 * Artifact registry —— agent tool 输出 → 渲染组件 的映射。
 *
 * 新增一种 agent 能力时：
 *   1. 在这里加一个 type
 *   2. 写对应的组件
 *   3. 注册进 ARTIFACT_REGISTRY
 * 其余代码（ChatPanel、Message 流）自动识别。
 */

export type ArtifactData = {
  "demo-metric-card": { label: string; value: string; delta?: number };
  // 后续扩展，例如：
  // "price-chart": { ticker: string; range: "1M" | "1Y"; series: number[] };
  // "financials-table": { ticker: string; rows: Record<string, number>[] };
  // "valuation": { ticker: string; method: "dcf" | "pb-pe"; fair_value: number };
};

export type ArtifactType = keyof ArtifactData;

export type Artifact<T extends ArtifactType = ArtifactType> = {
  id: string;
  type: T;
  data: ArtifactData[T];
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ArtifactComponent = FC<{ data: any }>;

export const ARTIFACT_REGISTRY: Record<ArtifactType, ArtifactComponent> = {
  "demo-metric-card": DemoMetricCard,
};

export function getArtifactComponent(
  type: ArtifactType
): ArtifactComponent | undefined {
  return ARTIFACT_REGISTRY[type];
}
