import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// One build serves both the Tauri window and `notepdf gui` (which serves src/notepdf/gui/dist).
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: './',
  clearScreen: false,
  build: {
    outDir: '../src/notepdf/gui/dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 1421,
    strictPort: true,
    // `npm run dev` in a browser talks to a backend started with `notepdf gui --no-browser`.
    proxy: { '/api': 'http://127.0.0.1:8766' },
  },
})
