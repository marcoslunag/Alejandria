import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Injected at build time — used to bust the service worker cache on each deploy
    __BUILD_TIME__: JSON.stringify(Date.now()),
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://backend:7878',
        changeOrigin: true,
      }
    }
  }
})
