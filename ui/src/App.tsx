import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'
import { AuthProvider } from './state/AuthContext'
import { ProductsPanel } from './components/ProductsPanel'
import { DeploymentsPanel } from './components/DeploymentsPanel'

function App() {
  return (
    <AuthProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/admin" element={<Admin />}>
            <Route index element={<Navigate to="products" replace />} />
            <Route path="products" element={<ProductsPanel />} />
            <Route path="deployments" element={<DeploymentsPanel />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </AuthProvider>
  )
}

export default App
