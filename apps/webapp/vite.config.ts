import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_BASE_URL || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      host: true,
      port: Number(env.VITE_DEV_PORT) || 5173,
      proxy: {
        "/api": { target: apiTarget, ws: true, changeOrigin: true },
      },
    },
  };
});
