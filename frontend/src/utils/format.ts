/** Locale-aware formatting. Arabic uses Latin digits for business readability. */
const locale = (lang: string) => (lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB");

export function formatNumber(value: number, lang: string, maximumFractionDigits = 1) {
  return new Intl.NumberFormat(locale(lang), { maximumFractionDigits }).format(value);
}

export function formatTime(iso: string, lang: string) {
  return new Intl.DateTimeFormat(locale(lang), { timeStyle: "medium" }).format(new Date(iso));
}

/** Amounts arrive from the API as decimal strings; they are only parsed for display. */
export function formatMoney(value: string | number | null | undefined, currency: string, lang: string) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(locale(lang), { style: "currency", currency, minimumFractionDigits: 2 }).format(Number(value));
}

export function formatQty(value: string | number | null | undefined, lang: string) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(locale(lang), { maximumFractionDigits: 3 }).format(Number(value));
}

export function formatDateTime(iso: string, lang: string) {
  return new Intl.DateTimeFormat(locale(lang), { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function formatDay(iso: string, lang: string) {
  return new Intl.DateTimeFormat(locale(lang), { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}
