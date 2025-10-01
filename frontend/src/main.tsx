import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { APP_CONFIG } from './config/app'

// HTMLタイトルを設定
document.title = APP_CONFIG.HTML_TITLE

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)