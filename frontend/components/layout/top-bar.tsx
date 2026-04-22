"use client";

import { MoonIcon, SearchIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { useT } from "@/lib/i18n";
import { MARKETS, useAppStore } from "@/lib/store";

type TopBarProps = {
  onOpenCommand: () => void;
};

export function TopBar({ onOpenCommand }: TopBarProps) {
  const t = useT();
  const market = useAppStore((s) => s.market);
  const setMarket = useAppStore((s) => s.setMarket);

  return (
    <header className="flex h-12 items-center gap-3 border-b bg-sidebar px-4">
      <div className="flex items-center gap-2">
        <div className="size-6 rounded-md bg-(color:--color-brand)" />
        <span className="text-sm font-semibold tracking-tight">
          {t("brand")}
        </span>
      </div>

      <Separator orientation="vertical" className="h-6" />

      <Tabs
        value={market}
        onValueChange={(v) => setMarket(v as typeof market)}
      >
        <TabsList className="h-8">
          {MARKETS.map((m) => (
            <TabsTrigger key={m} value={m} className="text-xs">
              {t(`market.${m}` as const)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="flex-1" />

      <Button
        variant="outline"
        size="sm"
        className="gap-2 text-muted-foreground"
        onClick={onOpenCommand}
      >
        <SearchIcon className="size-3.5" />
        <span>{t("top_bar.search_button")}</span>
        <kbd className="ml-2 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          ⌘K
        </kbd>
      </Button>

      <ThemeToggle />
    </header>
  );
}

function ThemeToggle() {
  const t = useT();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={t("top_bar.theme_aria")}
        disabled
      >
        <MoonIcon />
      </Button>
    );
  }

  const isDark = theme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={t("top_bar.theme_aria")}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}
