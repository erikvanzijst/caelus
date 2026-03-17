import { Box, Typography } from '@mui/material'
import { Outlet } from 'react-router-dom'
import { AdminSidebar } from '../components/AdminSidebar'

function Admin() {
  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h3">Admin</Typography>
        <Typography color="text.secondary">
          Manage products, template versions, and the canonical template selection.
        </Typography>
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
