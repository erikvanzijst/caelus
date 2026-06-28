/**
 * Design tokens and content data for the anonymous Freepod landing page.
 *
 * The landing page intentionally diverges from the utilitarian in-app theme:
 * a darker, editorial "digital sovereignty" aesthetic. Keeping the palette,
 * type stack and (provisional) content/pricing data in one module makes design
 * iteration fast and keeps the section components focused on layout.
 */
import type { SvgIconComponent } from '@mui/icons-material'
import PhotoLibraryRoundedIcon from '@mui/icons-material/PhotoLibraryRounded'
import FolderRoundedIcon from '@mui/icons-material/FolderRounded'
import ForumRoundedIcon from '@mui/icons-material/ForumRounded'
import GroupsRoundedIcon from '@mui/icons-material/GroupsRounded'
import LockRoundedIcon from '@mui/icons-material/LockRounded'

/* ── Type stack ──────────────────────────────────────────────────────────── */
/** Editorial serif for display headlines — gravitas, trust, character. */
export const DISPLAY = "'Fraunces Variable', 'Fraunces', Georgia, 'Times New Roman', serif"
/** European-feeling grotesque for body and UI. */
export const SANS = "'Schibsted Grotesk Variable', 'Schibsted Grotesk', system-ui, sans-serif"
/** Mono for eyebrow labels and small technical accents. */
export const MONO = "'Space Mono', ui-monospace, 'SFMono-Regular', monospace"

/* ── Palette ─────────────────────────────────────────────────────────────── */
export const ink = {
  /** Deepest background. */
  abyss: '#070A14',
  /** Primary background. */
  base: '#0B1020',
  /** Slightly raised panel base. */
  raised: '#10162B',
}

export const accent = {
  blue: '#5B8CFF',
  blueDeep: '#2563EB',
  cyan: '#38BDF8',
  magenta: '#EC4899',
  pink: '#F472B6',
}

export const fg = {
  primary: '#F4F6FB',
  muted: '#A6B0CC',
  faint: '#6F7C9B',
}

export const line = {
  soft: 'rgba(148, 163, 184, 0.14)',
  softer: 'rgba(148, 163, 184, 0.08)',
}

/** Glassy card surface used across sections. */
export const cardSurface = {
  background:
    'linear-gradient(160deg, rgba(255,255,255,0.055), rgba(255,255,255,0.018))',
  border: '1px solid rgba(255,255,255,0.08)',
  backdropFilter: 'blur(10px)',
}

/* ── Content data (honest, derived from the actual products) ─────────────── */
export interface AppEntry {
  name: string
  /** Short note when the running software differs from the brand. */
  engine?: string
  category: string
  replaces: string
  blurb: string
  icon: SvgIconComponent
  accent: string
}

export const APPS: AppEntry[] = [
  {
    name: 'Immich',
    category: 'Photos & video',
    replaces: 'Google Photos · iCloud Photos',
    blurb:
      'Automatic phone backup, lightning-fast search, albums and sharing for your entire library — without anyone mining your memories.',
    icon: PhotoLibraryRoundedIcon,
    accent: accent.blue,
  },
  {
    name: 'Nextcloud',
    category: 'Files & documents',
    replaces: 'Google Drive · Dropbox',
    blurb:
      'Sync files across every device, share links, and keep calendars and contacts together in one private workspace.',
    icon: FolderRoundedIcon,
    accent: accent.cyan,
  },
  {
    name: 'Matrix',
    engine: 'Tuwunel homeserver',
    category: 'Messaging',
    replaces: 'WhatsApp · Signal',
    blurb:
      'Your own homeserver on the open, federated Matrix network — end-to-end encrypted chat you actually control.',
    icon: ForumRoundedIcon,
    accent: accent.magenta,
  },
  {
    name: 'Mattermost',
    category: 'Team collaboration',
    replaces: 'Slack · Microsoft Teams',
    blurb:
      'Channels, threads and integrations for your team or community — self-hosted, ad-free, and yours to keep.',
    icon: GroupsRoundedIcon,
    accent: accent.pink,
  },
  {
    name: 'Vaultwarden',
    category: 'Passwords & passkeys',
    replaces: '1Password · LastPass',
    blurb:
      'A Bitwarden-compatible vault for passwords, passkeys and secrets, synced securely across all your devices.',
    icon: LockRoundedIcon,
    accent: accent.blue,
  },
]

/** Look up the marketing metadata for a product by its API name. */
export function appMetaByName(name: string): AppEntry | undefined {
  const needle = name.trim().toLowerCase()
  return APPS.find((app) => app.name.toLowerCase() === needle)
}

/** Rotating accents for products without dedicated marketing metadata. */
export const fallbackAccents = [accent.blue, accent.magenta, accent.cyan, accent.pink]
