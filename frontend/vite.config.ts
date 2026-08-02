import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://localhost:8000",
      "/telemetry": "http://localhost:8000",
      "/incidents": "http://localhost:8000",
      "/sim": "http://localhost:8000",
      "/network": "http://localhost:8000",
    },
  },
});
