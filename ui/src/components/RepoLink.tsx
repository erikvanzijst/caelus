import { Box } from '@mui/material'
import GitHubIcon from '@mui/icons-material/GitHub'
import { fg, MONO } from './landing/landingTokens'

export const REPO_URL = 'https://github.com/erikvanzijst/caelus'

export function RepoLink() {
  return (
    <Box
      component="a"
      href={REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="View the Freepod source code on GitHub"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.75,
        mt: 2.5,
        fontFamily: MONO,
        fontSize: 12.5,
        letterSpacing: '0.04em',
        color: fg.muted,
        transition: 'color 0.2s',
        '&:hover': { color: fg.primary },
      }}
    >
      <GitHubIcon sx={{ fontSize: 17 }} />
      Source on GitHub
    </Box>
  )
}

export default RepoLink
