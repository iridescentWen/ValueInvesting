"use client";

import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";
import { useT } from "@/lib/i18n";

export default function ScreenerPage() {
  const t = useT();
  return (
    <WorkspacePlaceholder
      title={t("pages.screener.title")}
      description={t("pages.screener.description")}
    />
  );
}
