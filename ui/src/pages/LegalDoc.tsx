import { useEffect } from 'react'
import { Link as RouterLink, Navigate, useParams } from 'react-router-dom'
import { Box, Button, Container, GlobalStyles, Stack } from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import PrintIcon from '@mui/icons-material/Print'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { LEGAL_DOCS } from '../content/legal'

/** Document-like styling for the rendered markdown, tuned for screen + print. */
const articleSx = {
  color: '#1f2933',
  fontSize: 16,
  lineHeight: 1.7,
  '& h1': { fontSize: '2rem', fontWeight: 700, lineHeight: 1.25, mt: 0, mb: 3, color: '#0d0f12' },
  '& h2': {
    fontSize: '1.4rem',
    fontWeight: 700,
    mt: 5,
    mb: 1.5,
    pb: 0.75,
    color: '#0d0f12',
    borderBottom: '1px solid #e5e7eb',
  },
  '& h3': { fontSize: '1.1rem', fontWeight: 700, mt: 3.5, mb: 1, color: '#0d0f12' },
  '& p': { my: 1.5 },
  '& ul, & ol': { pl: 3.5, my: 1.5 },
  '& li': { mb: 0.75 },
  '& a': { color: '#2563eb', textDecoration: 'underline' },
  '& strong': { fontWeight: 700, color: '#0d0f12' },
  '& hr': { border: 0, borderTop: '1px solid #e5e7eb', my: 4 },
  '& blockquote': {
    m: 0,
    my: 2,
    px: 2.5,
    py: 1,
    borderLeft: '4px solid #c7d2fe',
    bgcolor: '#f5f7ff',
    color: '#374151',
    borderRadius: '0 4px 4px 0',
    '& p': { my: 0.75 },
  },
  '& code': {
    fontFamily: '"Space Mono", ui-monospace, monospace',
    fontSize: '0.85em',
    bgcolor: '#f1f5f9',
    px: 0.5,
    py: 0.1,
    borderRadius: '4px',
  },
  '& table': {
    borderCollapse: 'collapse',
    width: '100%',
    my: 2,
    fontSize: '0.95rem',
    display: 'block',
    overflowX: 'auto',
  },
  '& th, & td': { border: '1px solid #d1d5db', px: 1.5, py: 1, textAlign: 'left', verticalAlign: 'top' },
  '& th': { bgcolor: '#f8fafc', fontWeight: 700 },
}

/** Hide on-screen chrome and reset the page background when printing. */
const printGlobals = (
  <GlobalStyles
    styles={{
      '@media print': {
        body: { background: '#fff !important' },
        '.legal-no-print': { display: 'none !important' },
      },
    }}
  />
)

/**
 * Public, print-friendly renderer for a single legal document. Rendered outside
 * the AppShell/landing chrome so it prints cleanly (browser "Save as PDF" yields
 * just the document). Available to anonymous and signed-in visitors alike.
 */
export function LegalDoc() {
  const { slug } = useParams<{ slug: string }>()
  const doc = slug ? LEGAL_DOCS[slug] : undefined

  useEffect(() => {
    if (!doc) return
    const previous = document.title
    document.title = `${doc.title} · Freepod`
    return () => {
      document.title = previous
    }
  }, [doc])

  // Client-side navigation preserves the window scroll offset, so a document
  // reached from the footer would otherwise open partway down. Reset to the top
  // whenever the document changes.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [slug])

  // Unknown slug → back to home rather than a blank page.
  if (!doc) return <Navigate to="/" replace />

  return (
    <Box sx={{ bgcolor: '#fff', minHeight: '100vh' }}>
      {printGlobals}
      <Box
        className="legal-no-print"
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 1,
          bgcolor: 'rgba(255,255,255,0.9)',
          backdropFilter: 'blur(8px)',
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <Container maxWidth="md">
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ py: 1.5 }}>
            <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />} size="small" sx={{ color: '#374151' }}>
              Back to Freepod
            </Button>
            <Button onClick={() => window.print()} startIcon={<PrintIcon />} size="small" variant="outlined">
              Print / Save as PDF
            </Button>
          </Stack>
        </Container>
      </Box>

      <Container maxWidth="md" sx={{ py: { xs: 4, md: 6 } }}>
        <Box sx={articleSx}>
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{
              // Open external links in a new tab; keep in-page anchors inline.
              a: ({ href, children, ...props }) => {
                const external = href?.startsWith('http')
                return (
                  <a
                    href={href}
                    {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                    {...props}
                  >
                    {children}
                  </a>
                )
              },
            }}
          >
            {doc.content}
          </Markdown>
        </Box>
      </Container>
    </Box>
  )
}

export default LegalDoc
