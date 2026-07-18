import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 개발 모드에서 FastAPI 백엔드(serve-gui, 기본 포트 8765)로 프록시.
      '/api': 'http://127.0.0.1:8765',
    },
  },
})
