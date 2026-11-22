import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'

const isWidgetMode = new URLSearchParams(window.location.search).get('widget') === 'true';

if (isWidgetMode) {
  document.body.classList.add('widget-mode');
  document.documentElement.classList.add('widget-mode');
  
  import('./components/Hotbar').then(({ default: Hotbar }) => {
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <Hotbar 
          isMicActive={false} 
          onMic={() => {}} 
          onSearch={() => {}} 
          onExpand={() => { window.location.href = 'aios://expand'; }} 
          onClose={() => { window.location.href = 'aios://close'; }} 
        />
      </React.StrictMode>,
    )
  });
} else {
  import('./App').then(({ default: App }) => {
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    )
  });
}
