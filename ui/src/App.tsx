import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import { AuthProvider, useAuth } from './state/AuthContext'
import { ProductsPanel } from './components/ProductsPanel'
import { DeploymentsPanel } from './components/DeploymentsPanel'
import { PlansPanel } from './components/PlansPanel'

/**
 * Auth-aware root: the same '/' URL serves the anonymous landing page to
 * visitors and the provisioning dashboard to signed-in users.
 */
function AuthedApp() {
  const { user, loading } = useAuth()

  // Avoid flashing the landing page while the initial /api/me check runs.
  if (loading) return null
  if (!user) return <Landing />

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/admin" element={<Admin />}>
          <Route index element={<Navigate to="products" replace />} />
          <Route path="products" element={<ProductsPanel />} />
          <Route path="deployments" element={<DeploymentsPanel />} />
          <Route path="plans" element={<PlansPanel />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}

function App() {
  return (
    <AuthProvider>
      <AuthedApp />
    </AuthProvider>
  )
}

export default App
