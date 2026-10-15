import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
  base: "/app/",
  build: { outDir: "../src/yuanjian_agent/ui", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.OPENGUARD_API_TARGET || "http://127.0.0.1:8002",
        changeOrigin: false,
      },
    },
  },
});
