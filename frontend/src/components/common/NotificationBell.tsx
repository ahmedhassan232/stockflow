import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useGet, useSend, type Page } from "@/features/data/api";
import { formatDateTime, formatQty } from "@/utils/format";

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  data: { quantity?: string; minimum_stock_level?: string } | null;
  read_at: string | null;
  created_at: string;
}

export function NotificationBell() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const query = useGet<Page<Notification> & { unread: number }>("/notifications", { page_size: 8 }, true, 60_000);
  const send = useSend(["notifications"]);
  const unread = query.data?.unread ?? 0;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <Button variant="outline" size="icon" className="relative size-9" aria-label={t("notifications.title", { count: unread })} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Bell />
        {unread > 0 ? <span className="absolute -end-1 -top-1 grid min-w-5 place-items-center rounded-full bg-danger px-1 text-[11px] font-bold leading-5 text-white">{unread > 9 ? "9+" : unread}</span> : null}
      </Button>
      {open ? (
        <div className="absolute end-0 top-11 z-30 w-80 max-w-[calc(100vw-2rem)] rounded-lg border bg-card shadow-xl">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <p className="text-sm font-semibold">{t("notifications.heading")}</p>
            {unread > 0 ? (
              <button type="button" className="text-xs text-secondary hover:underline" disabled={send.isPending} onClick={() => send.mutate({ path: "/notifications/read-all" })}>
                {t("notifications.markAll")}
              </button>
            ) : null}
          </div>
          <ul className="max-h-80 divide-y overflow-y-auto text-sm">
            {!query.data || query.data.items.length === 0 ? (
              <li className="p-6 text-center text-muted-foreground">{t("notifications.empty")}</li>
            ) : (
              query.data.items.map((n) => (
                <li key={n.id}>
                  <button type="button" disabled={!!n.read_at} onClick={() => send.mutate({ path: `/notifications/${n.id}/read` })} className={`block w-full px-4 py-3 text-start ${n.read_at ? "opacity-60" : "hover:bg-muted"}`}>
                    <span className="flex items-center gap-2 font-medium">
                      {!n.read_at ? <span className="size-2 shrink-0 rounded-full bg-danger" aria-hidden="true" /> : null}
                      {n.type === "low_stock" ? t("notifications.lowStock", { name: n.title }) : n.title}
                    </span>
                    {n.type === "low_stock" && n.data ? (
                      <span className="block text-xs text-muted-foreground">
                        {t("notifications.lowStockBody", { quantity: formatQty(n.data.quantity, i18n.language), minimum: formatQty(n.data.minimum_stock_level, i18n.language) })}
                      </span>
                    ) : null}
                    <span className="block text-xs text-muted-foreground">{formatDateTime(n.created_at, i18n.language)}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
