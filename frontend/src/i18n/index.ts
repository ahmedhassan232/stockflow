import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

export const LANGUAGES = { ar: { dir: "rtl" }, en: { dir: "ltr" } } as const;
export type Language = keyof typeof LANGUAGES;
export const DEFAULT_LANGUAGE: Language = "ar";
const STORAGE_KEY = "stockflow.lang";

function initialLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "ar" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return DEFAULT_LANGUAGE;
}

/** Keeps <html lang dir> in sync so layout direction is real, not just text-align. */
export function applyDocumentLanguage(lang: Language) {
  document.documentElement.lang = lang;
  document.documentElement.dir = LANGUAGES[lang].dir;
}

void i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  interpolation: { escapeValue: false },
});

applyDocumentLanguage(i18n.language as Language);
i18n.on("languageChanged", (lng) => {
  applyDocumentLanguage(lng as Language);
  try {
    localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    /* ignore */
  }
});

export default i18n;
