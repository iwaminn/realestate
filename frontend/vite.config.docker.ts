import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    host: '0.0.0.0',
    https: {
      key: fs.readFileSync('/app/certs/key.pem'),
      cert: fs.readFileSync('/app/certs/cert.pem'),
    },
    proxy: {
      '/api': {
        target: 'http://realestate-backend:8000',
        changeOrigin: true,
        secure: false,
        cookieDomainRewrite: '',
        cookiePathRewrite: '/',
      }
    }
  }
})
