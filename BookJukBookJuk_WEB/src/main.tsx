import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { resetTransientAgentRuntimeState } from './agent/runtime/resetAgentRuntime.ts'

resetTransientAgentRuntimeState()

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    resetTransientAgentRuntimeState()
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
