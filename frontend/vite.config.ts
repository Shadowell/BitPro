import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8888,
    proxy: {
      '/api': {
        target: 'http://localhost:8889',
        changeOrigin: true,
        ws: true,  // 代理 WebSocket
      },
    },
  },
})
