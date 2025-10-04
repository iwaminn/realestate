import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

export default defineConfig(({ command }) => {
  // 開発サーバー起動時のみHTTPS証明書を読み込む
  const serverConfig = command === 'serve' ? {
    port: 3001,
    host: '0.0.0.0',
    https: {
      key: fs.readFileSync(path.resolve(__dirname, '../certs/key.pem')),
      cert: fs.readFileSync(path.resolve(__dirname, '../certs/cert.pem')),
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://backend:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  } : {
    // ビルド時は証明書不要
    port: 3001,
    host: '0.0.0.0',
  };

  return {
    plugins: [react()],
    server: serverConfig
  };
})