"use client";

import {
  BarChart3Icon,
  GaugeIcon,
  GitCompareIcon,
  LineChartIcon,
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
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: typeof GaugeIcon;
  match: (pathname: string) => boolean;
};

const NAV_ITEMS: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: GaugeIcon,
    match: (p) => p === "/dashboard" || p === "/",
  },
  {
    href: "/screener",
    label: "筛选",
    icon: BarChart3Icon,
    match: (p) => p.startsWith("/screener"),
  },
  {
    href: "/compare",
    label: "对比",
    icon: GitCompareIcon,
    match: (p) => p.startsWith("/compare"),
  },
  {
    href: "/watchlist",
    label: "自选",
    icon: StarIcon,
    match: (p) => p.startsWith("/watchlist"),
  },
  {
    href: "/stock/AAPL",
    label: "个股 (demo)",
    icon: LineChartIcon,
    match: (p) => p.startsWith("/stock"),
  },
];

export function NavRail() {
  const pathname = usePathname();

  return (
    <TooltipProvider delayDuration={200}>
      <nav className="flex h-full w-14 flex-col items-center gap-1 border-r bg-sidebar py-3">
        {NAV_ITEMS.map((item) => {
          const active = item.match(pathname);
          const Icon = item.icon;
          return (
            <Tooltip key={item.href}>
              <TooltipTrigger asChild>
                <Link
                  href={item.href}
                  aria-label={item.label}
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
              <TooltipContent side="right">{item.label}</TooltipContent>
            </Tooltip>
          );
        })}
      </nav>
    </TooltipProvider>
  );
}
