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
import { useT } from "@/lib/i18n";
import { MARKETS, useAppStore } from "@/lib/store";

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
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
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("command.dialog_title")}
    >
      <CommandInput placeholder={t("command.placeholder")} />
      <CommandList>
        <CommandEmpty>{t("command.empty")}</CommandEmpty>

        <CommandGroup heading={t("command.group_nav")}>
          <CommandItem onSelect={() => run(() => router.push("/dashboard"))}>
            <GaugeIcon />
            <span>{t("command.open_dashboard")}</span>
          </CommandItem>
          <CommandItem onSelect={() => run(() => router.push("/screener"))}>
            <BarChart3Icon />
            <span>{t("command.open_screener")}</span>
          </CommandItem>
          <CommandItem onSelect={() => run(() => router.push("/watchlist"))}>
            <StarIcon />
            <span>{t("command.open_watchlist")}</span>
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t("command.group_market")}>
          {MARKETS.map((m) => (
            <CommandItem key={m} onSelect={() => run(() => setMarket(m))}>
              <GlobeIcon />
              <span>
                {t("command.switch_market_prefix")}
                {t(`market.${m}` as const)}
              </span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t("command.group_appearance")}>
          <CommandItem
            onSelect={() =>
              run(() => setTheme(theme === "dark" ? "light" : "dark"))
            }
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            <span>
              {theme === "dark"
                ? t("command.theme_to_light")
                : t("command.theme_to_dark")}
            </span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
