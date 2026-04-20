"use client";

import {
  BarChart3Icon,
  GaugeIcon,
  GlobeIcon,
  MoonIcon,
  StarIcon,
  SunIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { MARKETS, useAppStore } from "@/lib/store";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const setMarket = useAppStore((s) => s.setMarket);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const run = (fn: () => void) => {
    fn();
    onOpenChange(false);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="命令">
      <CommandInput placeholder="输入命令或搜索……" />
      <CommandList>
        <CommandEmpty>没有匹配项。</CommandEmpty>

        <CommandGroup heading="导航">
          <CommandItem onSelect={() => run(() => router.push("/dashboard"))}>
            <GaugeIcon />
            <span>打开 Dashboard</span>
          </CommandItem>
          <CommandItem onSelect={() => run(() => router.push("/screener"))}>
            <BarChart3Icon />
            <span>打开筛选器</span>
          </CommandItem>
          <CommandItem onSelect={() => run(() => router.push("/watchlist"))}>
            <StarIcon />
            <span>打开自选</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="切换市场">
          {MARKETS.map((m) => (
            <CommandItem
              key={m.value}
              onSelect={() => run(() => setMarket(m.value))}
            >
              <GlobeIcon />
              <span>切到 {m.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="外观">
          <CommandItem
            onSelect={() =>
              run(() => setTheme(theme === "dark" ? "light" : "dark"))
            }
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            <span>切换到 {theme === "dark" ? "浅色" : "深色"} 主题</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
