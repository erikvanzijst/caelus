import termsOfService from './terms-of-service.md?raw'
import acceptableUse from './acceptable-use-policy.md?raw'
import dataProcessing from './data-processing-agreement.md?raw'
import privacyPolicy from './privacy-policy.md?raw'

export interface LegalDoc {
  /** URL slug under /legal/:slug */
  slug: string
  /** Human-readable title (also used for the browser tab and footer link). */
  title: string
  /**
   * Document version, an ISO-8601 date parsed from the document's
   * `**Effective date:**` line. This is the value recorded when a user accepts
   * the terms; it changes only when the document is revised (unlike a commit
   * SHA) and is both human-readable and orderable.
   */
  version: string
  /** Raw markdown source, bundled at build time. */
  content: string
}

/** Matches the `**Effective date:** YYYY-MM-DD` line in each legal document. */
const EFFECTIVE_DATE_RE = /\*\*Effective date:\*\*\s*(\d{4}-\d{2}-\d{2})/

/**
 * Extract the document's version (its effective date) from the bundled
 * markdown, so the human-facing "Effective date" is the single source of truth.
 *
 * Throws at module load if a document has no parseable `YYYY-MM-DD` effective
 * date: a legal consent record must never silently capture an empty or wrong
 * version, so we fail the dev/CI build instead. (See the `index.test.ts` guard.)
 */
function versionOf(slug: string, markdown: string): string {
  const match = markdown.match(EFFECTIVE_DATE_RE)
  if (!match) {
    throw new Error(
      `Legal document "${slug}" is missing a valid **Effective date:** (YYYY-MM-DD) line`,
    )
  }
  return match[1]
}

/**
 * Registry of legal documents, keyed by URL slug. The markdown lives in this
 * same directory (canonical copy); the repo-root `legal/` directory holds
 * symlinks back to these files so the documents stay browsable there without
 * breaking the UI's Docker build, whose context is `ui/`.
 */
export const LEGAL_DOCS: Record<string, LegalDoc> = {
  terms: {
    slug: 'terms',
    title: 'Terms of Service',
    version: versionOf('terms', termsOfService),
    content: termsOfService,
  },
  privacy: {
    slug: 'privacy',
    title: 'Privacy Policy',
    version: versionOf('privacy', privacyPolicy),
    content: privacyPolicy,
  },
  aup: {
    slug: 'aup',
    title: 'Acceptable Use Policy',
    version: versionOf('aup', acceptableUse),
    content: acceptableUse,
  },
  dpa: {
    slug: 'dpa',
    title: 'Data Processing Agreement',
    version: versionOf('dpa', dataProcessing),
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
