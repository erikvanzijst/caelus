const dateFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function formatDateTime(value?: string | null) {
  if (!value) return '—'
  return dateFormatter.format(new Date(value))
}

export function ensureUrl(domain: string) {
  if (!domain) return '#'
  if (domain.startsWith('http://') || domain.startsWith('https://')) {
    return domain
  }
  return `https://${domain}`
}
