"use client";

import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";
import { useT } from "@/lib/i18n";

export default function ComparePage() {
  const t = useT();
  return (
    <WorkspacePlaceholder
      title={t("pages.compare.title")}
      description={t("pages.compare.description")}
    />
  );
}
