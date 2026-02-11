import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import Admin from './pages/Admin'
import Dashboard from './pages/Dashboard'

function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}

export default App
