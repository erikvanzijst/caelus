import { Box } from '@mui/material'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

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

interface LegalDocBodyProps {
  /** Raw markdown source of the legal document. */
  content: string
}

/**
 * Renders a legal document's markdown with the shared document styling. Reused
 * by the full-page `/legal/:slug` route and the in-dialog ToS reader modal, so
 * the two never drift apart.
 */
export function LegalDocBody({ content }: LegalDocBodyProps) {
  return (
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
        {content}
      </Markdown>
    </Box>
  )
}
