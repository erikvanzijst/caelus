import {
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Tooltip,
} from '@mui/material'
import {
  ChevronLeft,
  ChevronRight,
  Inventory2Outlined,
  LocalOfferOutlined,
  RocketLaunchOutlined,
} from '@mui/icons-material'
import { NavLink, useLocation } from 'react-router-dom'
import { useState } from 'react'
import type { CSSObject, Theme } from '@mui/material/styles'

const navItems = [
  { label: 'Products', path: '/admin/products', icon: <Inventory2Outlined /> },
  { label: 'Deployments', path: '/admin/deployments', icon: <RocketLaunchOutlined /> },
  { label: 'Plans', path: '/admin/plans', icon: <LocalOfferOutlined /> },
]

const DRAWER_WIDTH = 220

const openedMixin = (theme: Theme): CSSObject => ({
  width: DRAWER_WIDTH,
  transition: theme.transitions.create('width', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.enteringScreen,
  }),
  overflowX: 'hidden',
})

const closedMixin = (theme: Theme): CSSObject => ({
  width: `calc(${theme.spacing(7)} + 1px)`,
  transition: theme.transitions.create('width', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  overflowX: 'hidden',
})

export function AdminSidebar() {
  const location = useLocation()
  const [open, setOpen] = useState(true)

  return (
    <Drawer
      variant="permanent"
      open={open}
      sx={(theme) => ({
        flexShrink: 0,
        whiteSpace: 'nowrap',
        boxSizing: 'border-box',
        ...(open ? openedMixin(theme) : closedMixin(theme)),
        '& .MuiDrawer-paper': {
          position: 'relative',
          ...(open ? openedMixin(theme) : closedMixin(theme)),
        },
      })}
    >
      <List disablePadding>
        {navItems.map(({ label, path, icon }) => (
          <Tooltip key={path} title={open ? '' : label} placement="right">
            <ListItemButton
              component={NavLink}
              to={path}
              selected={location.pathname.startsWith(path)}
              sx={{
                minHeight: 48,
                px: 2.5,
                justifyContent: open ? 'initial' : 'center',
                '&.Mui-selected': { bgcolor: 'action.selected' },
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: 0,
                  mr: open ? 2 : 'auto',
                  justifyContent: 'center',
                }}
              >
                {icon}
              </ListItemIcon>
              <ListItemText
                primary={label}
                sx={{ opacity: open ? 1 : 0 }}
              />
            </ListItemButton>
          </Tooltip>
        ))}
      </List>
      <IconButton
        onClick={() => setOpen(!open)}
        sx={{ mx: 'auto', mt: 1 }}
        size="small"
      >
        {open ? <ChevronLeft /> : <ChevronRight />}
      </IconButton>
    </Drawer>
  )
}
