import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import '@fontsource-variable/inter'
import '@fontsource/instrument-serif'
import './index.css'

import App from './App'
import { PortfolioProvider } from './state/PortfolioContext'

// Opts the document into scroll-reveal hiding. Set here, synchronously, before
// React mounts — so if this bundle fails to execute at all, the attribute is
// absent, the hiding rule never matches, and every card renders visible instead
// of the page coming up blank.
document.documentElement.dataset.revealCapable = ''

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <PortfolioProvider>
        <App />
      </PortfolioProvider>
    </BrowserRouter>
  </StrictMode>,
)
