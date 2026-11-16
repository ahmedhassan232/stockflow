/** Exact decimal arithmetic for on-screen previews (cart totals etc.). Uses BigInt
 *  fixed-point, never floats, and the same ROUND_HALF_UP rule as the backend.
 *  The server still recomputes every amount – these values are display only. */
const SCALE = 6;
const UNIT = 10n ** BigInt(SCALE);

export function parse(value: string | number | null | undefined): bigint {
  const text = String(value ?? "0").trim();
  if (!/^-?\d*(\.\d*)?$/.test(text) || text === "" || text === "-" || text === ".") return 0n;
  const negative = text.startsWith("-");
  const [whole = "0", fraction = ""] = text.replace("-", "").split(".");
  const digits = BigInt(whole || "0") * UNIT + BigInt((fraction + "0".repeat(SCALE)).slice(0, SCALE) || "0");
  return negative ? -digits : digits;
}

function roundTo(value: bigint, places: number): bigint {
  const step = 10n ** BigInt(SCALE - places);
  const half = step / 2n;
  const adjusted = value >= 0n ? value + half : value - half;
  return (adjusted / step) * step;
}

export function toFixed(value: bigint, places = 2): string {
  const rounded = roundTo(value, places);
  const negative = rounded < 0n;
  const abs = negative ? -rounded : rounded;
  const whole = abs / UNIT;
  const fraction = (abs % UNIT).toString().padStart(SCALE, "0").slice(0, places);
  return `${negative ? "-" : ""}${whole}${places ? `.${fraction}` : ""}`;
}

export const mul = (a: bigint, b: bigint) => (a * b) / UNIT;
export const money = (value: bigint) => roundTo(value, 2);

export interface LinePreview {
  gross: bigint;
  discount: bigint;
  tax: bigint;
  total: bigint;
}

export function linePreview(quantity: string, unitPrice: string, taxRate: string, discount = "0"): LinePreview {
  const gross = money(mul(parse(quantity), parse(unitPrice)));
  const disc = money(parse(discount));
  const tax = money(mul(gross - disc, parse(taxRate)) / 100n);
  return { gross, discount: disc, tax, total: gross - disc + tax };
}

export const isPositive = (value: string) => parse(value) > 0n;
export const compare = (a: string, b: string) => (parse(a) === parse(b) ? 0 : parse(a) > parse(b) ? 1 : -1);
