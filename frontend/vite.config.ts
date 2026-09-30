/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const apiTarget = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8001";
const proxy = { "/api": { target: apiTarget, changeOrigin: false } };

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      includeAssets: ["favicon.svg", "icons/*.png"],
      manifest: {
        name: "Lumina",
        short_name: "Lumina",
        description: "Source-backed answers from approved hospital protocols (synthetic demo corpus).",
        theme_color: "#0b6e8a",
        background_color: "#f6f7f9",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Offline shell: the app loads without a network; answers still need the server.
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/],
        globPatterns: ["**/*.{js,mjs,css,html,svg,png,woff2}"],
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        runtimeCaching: [
          {
            // The last 20 viewed sources stay readable offline (cleared on sign-out).
            urlPattern: ({ url, request }) =>
              url.pathname.startsWith("/api/v1/sources/") && request.method === "GET",
            handler: "NetworkFirst",
            options: {
              cacheName: "protocite-sources",
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 20 },
              cacheableResponse: { statuses: [200] },
            },
          },
        ],
      },
    }),
  ],
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 5173, strictPort: true, proxy },
  build: { sourcemap: true, chunkSizeWarningLimit: 1500 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
