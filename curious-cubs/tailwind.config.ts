import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: "#FFF8F0",
        sunshine: "#FFC93C",
        coral: "#FF6B57",
        teal: "#0E9594",
        navy: "#155263",
        blush: "#FFE8E0",
      },
      fontFamily: {
        display: ['"Baloo 2"', '"Comic Sans MS"', "system-ui", "sans-serif"],
        body: ['"Nunito"', "system-ui", "-apple-system", "sans-serif"],
      },
      boxShadow: {
        card: "0 8px 24px rgba(21, 82, 99, 0.10)",
        pop: "0 4px 0 rgba(21, 82, 99, 0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
