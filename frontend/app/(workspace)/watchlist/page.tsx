"use client";

import { WorkspacePlaceholder } from "@/components/layout/workspace-placeholder";
import { useT } from "@/lib/i18n";

export default function WatchlistPage() {
  const t = useT();
  return (
    <WorkspacePlaceholder
      title={t("pages.watchlist.title")}
      description={t("pages.watchlist.description")}
    />
  );
}
