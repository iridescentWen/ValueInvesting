"use client";

import { MoonIcon, SearchIcon, SettingsIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { MARKETS, useAppStore } from "@/lib/store";

type TopBarProps = {
  onOpenCommand: () => void;
};

export function TopBar({ onOpenCommand }: TopBarProps) {
  const market = useAppStore((s) => s.market);
  const setMarket = useAppStore((s) => s.setMarket);

  return (
    <header className="flex h-12 items-center gap-3 border-b bg-sidebar px-4">
      <div className="flex items-center gap-2">
        <div className="size-6 rounded-md bg-(color:--color-brand)" />
        <span className="text-sm font-semibold tracking-tight">
          ValueInvesting
        </span>
      </div>

      <Separator orientation="vertical" className="h-6" />

      <Tabs
        value={market}
        onValueChange={(v) => setMarket(v as typeof market)}
      >
        <TabsList className="h-8">
          {MARKETS.map((m) => (
            <TabsTrigger key={m.value} value={m.value} className="text-xs">
              {m.label}
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
        <span>搜索 / 命令</span>
        <kbd className="ml-2 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          ⌘K
        </kbd>
      </Button>

      <ThemeToggle />

      <Button variant="ghost" size="icon-sm" aria-label="Settings">
        <SettingsIcon />
      </Button>
    </header>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon-sm" aria-label="Toggle theme" disabled>
        <MoonIcon />
      </Button>
    );
  }

  const isDark = theme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}
