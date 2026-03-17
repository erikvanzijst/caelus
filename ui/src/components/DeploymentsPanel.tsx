import { Box, Typography } from '@mui/material'
import { RocketLaunchOutlined } from '@mui/icons-material'

export function DeploymentsPanel() {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py: 10,
        color: 'text.secondary',
      }}
    >
      <RocketLaunchOutlined sx={{ fontSize: 48, mb: 2, opacity: 0.4 }} />
      <Typography variant="h6">Deployments</Typography>
      <Typography variant="body2">Coming soon.</Typography>
    </Box>
  )
}
