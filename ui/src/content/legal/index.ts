import termsOfService from './terms-of-service.md?raw'
import acceptableUse from './acceptable-use-policy.md?raw'
import dataProcessing from './data-processing-agreement.md?raw'
import privacyPolicy from './privacy-policy.md?raw'

export interface LegalDoc {
  /** URL slug under /legal/:slug */
  slug: string
  /** Human-readable title (also used for the browser tab and footer link). */
  title: string
  /** Raw markdown source, bundled at build time. */
  content: string
}

/**
 * Registry of legal documents, keyed by URL slug. The markdown lives in this
 * same directory (canonical copy); the repo-root `legal/` directory holds
 * symlinks back to these files so the documents stay browsable there without
 * breaking the UI's Docker build, whose context is `ui/`.
 */
export const LEGAL_DOCS: Record<string, LegalDoc> = {
  terms: { slug: 'terms', title: 'Terms of Service', content: termsOfService },
  privacy: { slug: 'privacy', title: 'Privacy Policy', content: privacyPolicy },
  aup: { slug: 'aup', title: 'Acceptable Use Policy', content: acceptableUse },
  dpa: {
    slug: 'dpa',
    title: 'Data Processing Agreement',
    content: dataProcessing,
  },
}

/** Ordered list for footer/navigation rendering. */
export const LEGAL_NAV: LegalDoc[] = [
  LEGAL_DOCS.terms,
  LEGAL_DOCS.privacy,
  LEGAL_DOCS.aup,
  LEGAL_DOCS.dpa,
]
