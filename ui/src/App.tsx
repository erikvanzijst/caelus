import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import LegalDoc from './pages/LegalDoc'
import { AuthProvider, useAuth } from './state/AuthContext'
import { ProductsPanel } from './components/ProductsPanel'
import { DeploymentsPanel } from './components/DeploymentsPanel'
import { PlansPanel } from './components/PlansPanel'

/** Layout route that wraps the signed-in app pages in the AppShell chrome. */
function AppShellLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  )
}

/**
 * Auth-aware root: the same '/' URL serves the anonymous landing page to
 * visitors and the provisioning dashboard to signed-in users. Legal documents
 * live at /legal/:slug and render bare (outside the AppShell/landing chrome) so
 * they print cleanly and stay reachable whether or not the visitor is signed in.
 */
function AuthedApp() {
  const { user, loading } = useAuth()

  // Avoid flashing the landing page while the initial /api/me check runs.
  if (loading) return null

  return (
    <Routes>
      <Route path="/legal/:slug" element={<LegalDoc />} />
      {user ? (
        <Route element={<AppShellLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/admin" element={<Admin />}>
            <Route index element={<Navigate to="products" replace />} />
            <Route path="products" element={<ProductsPanel />} />
            <Route path="deployments" element={<DeploymentsPanel />} />
            <Route path="plans" element={<PlansPanel />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      ) : (
        <Route path="*" element={<Landing />} />
      )}
    </Routes>
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
