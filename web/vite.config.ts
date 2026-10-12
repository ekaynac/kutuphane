import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by Kütüphane Core under /ui; the API is same-origin (/v1). In dev, Vite proxies /v1 to the Core.
export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
  server: { proxy: { "/v1": "http://127.0.0.1:8080" } },
});
