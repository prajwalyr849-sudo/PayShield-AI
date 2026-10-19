import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AllCommunityModule, ModuleRegistry, provideGlobalGridOptions } from 'ag-grid-community'
import './index.css'
import App from './App.jsx'

// AG Grid v33+ requires feature modules (pagination, filters, row selection,
// quick filter) to be registered explicitly; without this the grid logs
// errors and silently ignores those options.
ModuleRegistry.registerModules([AllCommunityModule])
// The grids style themselves with the legacy CSS files (ag-grid.css +
// ag-theme-quartz.css), so mark every grid as legacy-themed to avoid the
// "Theming API and CSS File Themes are both used" console error (#239).
provideGlobalGridOptions({ theme: 'legacy' })

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
