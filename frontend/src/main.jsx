import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

// Register service worker for PWA.
// The ?v= query param changes on every build so the browser always fetches the
// latest sw.js and treats it as a new worker — this triggers cache invalidation.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register(`/sw.js?v=${__BUILD_TIME__}`)
      .then((reg) => console.log('SW registered', reg.scope))
      .catch((err) => console.warn('SW registration failed', err))
  })
}
