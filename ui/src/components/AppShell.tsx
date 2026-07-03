import {
  AppBar,
  Box,
  Button,
  Chip,
  Container,
  Divider,
  Menu,
  MenuItem,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material'
import { useState, type PropsWithChildren } from 'react'
import { NavLink } from 'react-router-dom'
import EmailDialog from './EmailDialog'
import { useAuth } from '../state/AuthContext'
import AuroraBackground from './landing/AuroraBackground'
import AppFooter from './AppFooter'
import { DISPLAY, fg } from './landing/landingTokens'

const keycloakAccountUrl = import.meta.env.VITE_KEYCLOAK_ACCOUNT_URL as
  | string
  | undefined

function AppShell({ children }: PropsWithChildren) {
  const { user, loading, email, setEmail } = useAuth()
  const showDialog = !loading && !user
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null)

  function handleLogout() {
    if (keycloakAccountUrl) {
      // Production: sign out through oauth2-proxy → Keycloak
      window.location.href =
        '/oauth2/sign_out?rd=' + encodeURIComponent(window.location.origin + '/')
    } else {
      // No Keycloak configured: clear email via React state to show the
      // email dialog without a page reload.
      setEmail('')
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Dimmed aurora, fixed to the viewport so it sits calmly behind scrolling
          content and ties the app to the landing page's atmosphere. */}
      <Box
        sx={{
          position: 'fixed',
          inset: 0,
          zIndex: 0,
          pointerEvents: 'none',
        }}
      >
        <AuroraBackground preset="whisper" subtle />
      </Box>
      <AppBar elevation={0} position="sticky">
        <Toolbar sx={{ gap: 2 }}>
          <Stack
            component={NavLink}
            to="/"
            direction="row"
            alignItems="center"
            spacing={1.25}
            sx={{ textDecoration: 'none' }}
          >
            <Box
              component="img"
              src="/caelus.svg"
              alt="Freepod"
              sx={{ width: 30, height: 30 }}
            />
            <Typography
              sx={{
                fontFamily: DISPLAY,
                fontWeight: 600,
                fontSize: 22,
                letterSpacing: '-0.02em',
                color: fg.primary,
              }}
            >
              Freepod
            </Typography>
          </Stack>
          <Box sx={{ flex: 1 }} />
          <Stack direction="row" spacing={1}>
            <Button
              component={NavLink}
              to="/"
              end
              variant="text"
              sx={{
                color: fg.muted,
                '&:hover': { color: fg.primary, background: 'rgba(255,255,255,0.04)' },
                '&.active': { color: fg.primary, background: 'rgba(255,255,255,0.06)' },
              }}
            >
              Dashboard
            </Button>
            {user?.is_admin && (
              <Button
                component={NavLink}
                to="/admin"
                variant="text"
                sx={{
                  color: fg.muted,
                  '&:hover': { color: fg.primary, background: 'rgba(255,255,255,0.04)' },
                  '&.active': { color: fg.primary, background: 'rgba(255,255,255,0.06)' },
                }}
              >
                Admin
              </Button>
            )}
          </Stack>
          <Box sx={{ flex: 1 }} />
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={user ? user.email : 'No email set'}
              variant="outlined"
              onClick={(e) => setMenuAnchor(e.currentTarget)}
              sx={{ bgcolor: 'rgba(255,255,255,0.03)', cursor: 'pointer' }}
            />
            <Menu
              anchorEl={menuAnchor}
              open={Boolean(menuAnchor)}
              onClose={() => setMenuAnchor(null)}
            >
              {keycloakAccountUrl && (
                <MenuItem
                  component="a"
                  href={keycloakAccountUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMenuAnchor(null)}
                >
                  Profile
                </MenuItem>
              )}
              {keycloakAccountUrl && <Divider />}
              <MenuItem onClick={handleLogout}>Logout</MenuItem>
            </Menu>
          </Stack>
        </Toolbar>
      </AppBar>
      <Container
        maxWidth="xl"
        sx={{ py: 6, position: 'relative', zIndex: 1, flex: 1 }}
      >
        {children}
      </Container>
      <AppFooter isAdmin={Boolean(user?.is_admin)} />
      <EmailDialog
        open={showDialog}
        current={email}
        onSave={(value) => {
          setEmail(value)
        }}
      />
    </Box>
  )
}

export default AppShell
