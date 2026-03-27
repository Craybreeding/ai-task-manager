import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/ai-captain-dashboard/',
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 4174,
    proxy: {
      '/ai-captain-dashboard/api': {
        target: 'http://localhost:4175',
        rewrite: (path) => path.replace(/^\/ai-captain-dashboard/, ''),
      },
    },
  },
})
