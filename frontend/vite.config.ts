import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
      '/stream': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: true,
      },
    },
    host: true,
    port: 8001,
    strictPort: true
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
})
