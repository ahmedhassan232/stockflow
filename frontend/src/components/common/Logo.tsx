export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden="true">
        <rect width="32" height="32" rx="8" className="fill-primary" />
        <path
          d="M16 6 6.5 11v10L16 26l9.5-5V11L16 6Zm0 2.7 6.3 3.3L16 15.3 9.7 12 16 8.7ZM9 14.1l5.8 3v5.6L9 19.6v-5.5Zm8.2 8.6v-5.6l5.8-3v5.5l-5.8 3.1Z"
          className="fill-primary-foreground"
        />
      </svg>
      <span className="text-lg font-bold tracking-tight">StockFlow</span>
    </span>
  );
}
