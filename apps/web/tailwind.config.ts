import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "var(--bg-primary)",
          card: "var(--bg-card)",
          elevated: "var(--bg-elevated)",
        },
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
        },
        accent: {
          blue: "var(--accent-blue)",
          green: "var(--accent-green)",
          amber: "var(--accent-amber)",
          red: "var(--accent-red)",
        },
        border: "var(--border)",
      },
      fontFamily: {
        display: ["Syne", "sans-serif"],
        body: ["Inter", "sans-serif"],
      },
      boxShadow: {
        hero: "0 30px 80px rgba(0,0,0,0.35)",
      },
      backgroundImage: {
        aurora:
          "radial-gradient(circle at top left, rgba(79,142,247,0.35), transparent 35%), radial-gradient(circle at 80% 20%, rgba(61,186,126,0.2), transparent 30%), linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0))",
      },
    },
  },
  plugins: [],
} satisfies Config;

