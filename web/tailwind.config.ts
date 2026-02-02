import type { Config } from "tailwindcss";

export default {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        supabase: {
          green: "#3ECF8E",
          "green-dark": "#2da36e",
        },
        dark: {
          bg: "#1a1a1a",
          card: "#242424",
          border: "#333333",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
