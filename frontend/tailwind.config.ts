import type { Config } from "tailwindcss";

const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1200px" } },
    extend: {
      colors: {
        background: token("background"),
        foreground: token("foreground"),
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        success: token("success"),
        warning: token("warning"),
        danger: token("danger"),
        info: token("info"),
        border: token("border"),
        ring: token("ring"),
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      fontFamily: {
        sans: ['"IBM Plex Sans Arabic"', '"Segoe UI"', "Tahoma", "system-ui", "-apple-system", "sans-serif"],
      },
      boxShadow: { card: "0 1px 2px rgb(15 31 61 / 0.05), 0 4px 16px rgb(15 31 61 / 0.04)" },
    },
  },
  plugins: [],
} satisfies Config;
