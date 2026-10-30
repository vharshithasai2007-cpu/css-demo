import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/css-api': {
        target: process.env.VITE_CSS_PROXY_TARGET || 'http://127.0.0.1:8101',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/css-api/, ''),
      },
    },
  },
})
