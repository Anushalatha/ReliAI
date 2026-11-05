/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#090B12",
        panel: "#10141F",
        line: "#242B3A",
        muted: "#8791A5",
        violet: "#8170FF",
        cyan: "#52D6E8",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 12px 32px rgba(0,0,0,.18)",
      },
    },
  },
  plugins: [],
};
