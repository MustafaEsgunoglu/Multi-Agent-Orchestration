import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: {
          bg: "#0b0f19",
          grid: "#1e293b",
          surface: "#111827",
          border: "#1f2937",
        },
      },
    },
  },
  plugins: [],
};

export default config;
