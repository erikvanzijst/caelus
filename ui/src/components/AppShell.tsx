import {
  AppBar,
  Avatar,
  Box,
  Button,
  Chip,
  Container,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material'
import type { PropsWithChildren } from 'react'
import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import EmailDialog from './EmailDialog'
import { useAuthEmail } from '../state/useAuthEmail'

function AppShell({ children }: PropsWithChildren) {
  const { email, setEmail } = useAuthEmail()
  const [dialogOpen, setDialogOpen] = useState(!email)

  return (
    <Box sx={{ minHeight: '100vh', position: 'relative' }}>
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            position: 'absolute',
            width: 380,
            height: 380,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(99,102,241,0.3), transparent 70%)',
            top: -120,
            left: -80,
          }}
        />
        <Box
          sx={{
            position: 'absolute',
            width: 280,
            height: 280,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(236,72,153,0.25), transparent 70%)',
            bottom: -120,
            right: -60,
          }}
        />
      </Box>
      <AppBar elevation={0} position="sticky">
        <Toolbar sx={{ gap: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Avatar sx={{ bgcolor: 'primary.main', width: 36, height: 36 }}>C</Avatar>
            <Box>
              <Typography variant="h6">Caelus Control</Typography>
              <Typography variant="caption" color="text.secondary">
                Provisioning cockpit
              </Typography>
            </Box>
          </Stack>
          <Box sx={{ flex: 1 }} />
          <Stack direction="row" spacing={1}>
            <Button
              component={NavLink}
              to="/"
              variant="outlined"
              color="primary"
              sx={{ borderColor: 'rgba(37, 99, 235, 0.4)' }}
            >
              Dashboard
            </Button>
            <Button
              component={NavLink}
              to="/admin"
              variant="outlined"
              color="secondary"
              sx={{ borderColor: 'rgba(236, 72, 153, 0.35)' }}
            >
              Admin
            </Button>
          </Stack>
          <Box sx={{ flex: 1 }} />
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={email ? `Signed in as ${email}` : 'No email set'}
              variant="outlined"
              sx={{ bgcolor: 'rgba(15, 23, 42, 0.04)' }}
            />
            <Button variant="contained" onClick={() => setDialogOpen(true)}>
              Switch
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 6, position: 'relative', zIndex: 1 }}>
        {children}
      </Container>
      <EmailDialog
        open={dialogOpen || !email}
        current={email}
        onSave={(value) => {
          setEmail(value)
          setDialogOpen(false)
        }}
      />
    </Box>
  )
}

export default AppShell
