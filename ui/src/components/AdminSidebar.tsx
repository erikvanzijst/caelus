import { Box, List, ListItemButton, ListItemIcon, ListItemText } from '@mui/material'
import { Inventory2Outlined, RocketLaunchOutlined } from '@mui/icons-material'
import { NavLink, useLocation } from 'react-router-dom'

const navItems = [
  { label: 'Products', path: '/admin/products', icon: <Inventory2Outlined /> },
  { label: 'Deployments', path: '/admin/deployments', icon: <RocketLaunchOutlined /> },
]

export const SIDEBAR_WIDTH = 220

export function AdminSidebar() {
  const location = useLocation()

  return (
    <Box
      sx={{
        width: SIDEBAR_WIDTH,
        flexShrink: 0,
        borderRight: 1,
        borderColor: 'divider',
      }}
    >
      <List disablePadding>
        {navItems.map(({ label, path, icon }) => (
          <ListItemButton
            key={path}
            component={NavLink}
            to={path}
            selected={location.pathname.startsWith(path)}
            sx={{
              '&.Mui-selected': {
                bgcolor: 'action.selected',
              },
            }}
          >
            <ListItemIcon sx={{ minWidth: 36 }}>{icon}</ListItemIcon>
            <ListItemText primary={label} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  )
}
