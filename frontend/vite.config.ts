import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts: ["frontend"],
    proxy: {
      "/updates-api": {
        target: "http://updates:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/updates-api/, ""),
        timeout: 30_000,
        proxyTimeout: 30_000,
      },
      "/api": {
        target: "http://app:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        timeout: 960_000,
        proxyTimeout: 960_000,
      },
    },
  },
});
