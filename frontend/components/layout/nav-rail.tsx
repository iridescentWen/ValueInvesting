"use client";

import {
  BarChart3Icon,
  GaugeIcon,
  GitCompareIcon,
  LineChartIcon,
  SettingsIcon,
  StarIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type TKey, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  labelKey: TKey;
  icon: typeof GaugeIcon;
  match: (pathname: string) => boolean;
};

const NAV_ITEMS: NavItem[] = [
  {
    href: "/dashboard",
    labelKey: "nav.dashboard",
    icon: GaugeIcon,
    match: (p) => p === "/dashboard" || p === "/",
  },
  {
    href: "/screener",
    labelKey: "nav.screener",
    icon: BarChart3Icon,
    match: (p) => p.startsWith("/screener"),
  },
  {
    href: "/compare",
    labelKey: "nav.compare",
    icon: GitCompareIcon,
    match: (p) => p.startsWith("/compare"),
  },
  {
    href: "/watchlist",
    labelKey: "nav.watchlist",
    icon: StarIcon,
    match: (p) => p.startsWith("/watchlist"),
  },
  {
    href: "/stock/AAPL",
    labelKey: "nav.stock_demo",
    icon: LineChartIcon,
    match: (p) => p.startsWith("/stock"),
  },
  {
    href: "/settings",
    labelKey: "nav.settings",
    icon: SettingsIcon,
    match: (p) => p.startsWith("/settings"),
  },
];

export function NavRail() {
  const pathname = usePathname();
  const t = useT();

  return (
    <TooltipProvider delayDuration={200}>
      <nav className="flex h-full w-14 flex-col items-center gap-1 border-r bg-sidebar py-3">
        {NAV_ITEMS.map((item) => {
          const active = item.match(pathname);
          const Icon = item.icon;
          const label = t(item.labelKey);
          return (
            <Tooltip key={item.href}>
              <TooltipTrigger asChild>
                <Link
                  href={item.href}
                  aria-label={label}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex size-10 items-center justify-center rounded-md text-muted-foreground transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    active &&
                      "bg-accent text-foreground shadow-inner ring-1 ring-border"
                  )}
                >
                  <Icon className="size-4" />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">{label}</TooltipContent>
            </Tooltip>
          );
        })}
      </nav>
    </TooltipProvider>
  );
}
