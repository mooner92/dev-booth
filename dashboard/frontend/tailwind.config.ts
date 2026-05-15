import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Seed Design tokens
        brand: {
          50: "#FFF4EE",
          100: "#FFE6D6",
          200: "#FFC299",
          300: "#FFA366",
          400: "#FF8533",
          500: "#FF6F0F",
          600: "#E65F0A",
          700: "#CC5008",
          800: "#A03F06",
          900: "#732D04",
          DEFAULT: "#FF6F0F",
        },
        seed: {
          primary: "#FF6F0F",
          primaryBg: "#FFF4EE",
          success: "#00B493",
          error: "#FF4136",
          warning: "#FF9800",
          info: "#0070F3",
        },
        agent: {
          conductor: "#FF4136",
          "architect": "#0070F3",
          "executor": "#00B493",
          system: "#6B7280",
        },
        neutral: {
          0: "#FFFFFF",
          50: "#F9FAFB",
          100: "#F4F4F4",
          200: "#E5E8EB",
          300: "#D4D4D8",
          400: "#ADB1BA",
          500: "#6B7280",
          600: "#4D5159",
          700: "#3F3F46",
          800: "#27272A",
          900: "#1A1C1E",
        },
        background: "var(--background)",
        foreground: "var(--foreground)",
        muted: { DEFAULT: "var(--muted)", foreground: "var(--muted-foreground)" },
        card: { DEFAULT: "var(--card)", foreground: "var(--card-foreground)" },
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
      },
      fontFamily: {
        sans: ["var(--font-pretendard)", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        xs: ["12px", { lineHeight: "16px" }],
        sm: ["14px", { lineHeight: "20px" }],
        base: ["16px", { lineHeight: "24px" }],
        lg: ["18px", { lineHeight: "28px" }],
        xl: ["20px", { lineHeight: "28px" }],
        "2xl": ["24px", { lineHeight: "32px" }],
        "3xl": ["28px", { lineHeight: "36px" }],
        "4xl": ["32px", { lineHeight: "40px" }],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "8px",
        md: "12px",
        lg: "16px",
        full: "999px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0, 0, 0, 0.08)",
        cardHover: "0 4px 12px rgba(0, 0, 0, 0.10)",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
