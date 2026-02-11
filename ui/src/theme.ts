import { createTheme } from '@mui/material/styles'

declare module '@mui/material/styles' {
  interface Palette {
    surface: Palette['primary']
  }
  interface PaletteOptions {
    surface?: PaletteOptions['primary']
  }
}

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#2563eb',
      light: '#7aa2ff',
      dark: '#1b3ea4',
      contrastText: '#f8fbff',
    },
    secondary: {
      main: '#ec4899',
      light: '#f8a5c9',
      dark: '#b4236c',
    },
    background: {
      default: '#f7f4ff',
      paper: '#ffffff',
    },
    surface: {
      main: '#0f172a',
      contrastText: '#ffffff',
    },
    text: {
      primary: '#0f172a',
      secondary: '#475569',
    },
  },
  typography: {
    fontFamily: '"Space Grotesk", "Space Mono", system-ui, sans-serif',
    h1: { fontWeight: 600, letterSpacing: -1 },
    h2: { fontWeight: 600, letterSpacing: -0.8 },
    h3: { fontWeight: 600, letterSpacing: -0.6 },
    h4: { fontWeight: 600, letterSpacing: -0.4 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: {
    borderRadius: 16,
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          border: '1px solid rgba(148, 163, 184, 0.25)',
          backdropFilter: 'blur(12px)',
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          borderRadius: 999,
          paddingInline: 18,
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'rgba(255, 255, 255, 0.86)',
          color: '#0f172a',
          borderBottom: '1px solid rgba(148, 163, 184, 0.3)',
          backdropFilter: 'blur(16px)',
        },
      },
    },
  },
})
