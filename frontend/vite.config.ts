import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 로컬 에이전트(backend/app.py)로 넘긴다
const agent = 'http://127.0.0.1:47821'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': agent,
    },
  },
})
