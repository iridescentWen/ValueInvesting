"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LOCALES, type Locale, useT } from "@/lib/i18n";
import { useAppStore } from "@/lib/store";

export default function SettingsPage() {
  const t = useT();
  const locale = useAppStore((s) => s.locale);
  const setLocale = useAppStore((s) => s.setLocale);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {t("settings.title")}
        </h1>
      </div>

      <div className="rounded-lg border">
        <div className="flex items-center justify-between px-4 py-4">
          <div>
            <div className="text-sm font-medium">
              {t("settings.language_label")}
            </div>
          </div>
          <Select
            value={locale}
            onValueChange={(v) => setLocale(v as Locale)}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOCALES.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );
}
