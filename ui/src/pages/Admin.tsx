import { Box } from '@mui/material'
import { Outlet } from 'react-router-dom'
import { AdminSidebar } from '../components/AdminSidebar'
import { PageHeading } from '../components/PageHeading'

function Admin() {
  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <PageHeading
          eyebrow="Control room"
          title="Admin"
          subtitle="Manage products, template versions, and the canonical template selection."
        />
      </Box>
      <Box sx={{ display: 'flex', gap: 3 }}>
        <AdminSidebar />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}

export default Admin
