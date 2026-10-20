import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { viteStaticCopy } from "vite-plugin-static-copy"

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    viteStaticCopy({
      // v4 keeps the source path under dest unless stripped; pdf.js expects
      // flat folders (e.g. /pdfjs/wasm/jbig2.wasm for JBIG2 scans).
      targets: [
        {
          src: "node_modules/pdfjs-dist/cmaps/*",
          dest: "pdfjs/cmaps",
          rename: { stripBase: true },
        },
        {
          src: "node_modules/pdfjs-dist/standard_fonts/*",
          dest: "pdfjs/standard_fonts",
          rename: { stripBase: true },
        },
        {
          src: "node_modules/pdfjs-dist/wasm/*",
          dest: "pdfjs/wasm",
          rename: { stripBase: true },
        },
      ],
    }),
  ],
  server: {
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "./src"),
    },
  },
})
