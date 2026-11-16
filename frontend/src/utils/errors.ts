import type { TFunction } from "i18next";
import { ApiError } from "@/services/api";

/** Maps backend error codes to localized text; falls back to a generic message. */
export function errorMessage(err: unknown, t: TFunction): string {
  if (err instanceof ApiError) {
    const key = `errors.${err.code}`;
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return t("errors.generic");
}
