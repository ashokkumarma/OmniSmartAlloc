import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built into dist/, which demo/server.py serves on http://localhost:8902.
// `npm run dev` serves on :5173 and forwards /api to the running demo server.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: { port: 5173, proxy: { "/api": "http://localhost:8902" } },
});
