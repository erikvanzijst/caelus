import { Box, Skeleton, Stack, Typography } from '@mui/material'
import Markdown from 'react-markdown'

export function formatPlanPrice(priceCents: number, interval: string): string {
  const amount = (priceCents / 100).toFixed(priceCents % 100 === 0 ? 0 : 2)
  const suffix = interval === 'annual' ? '/yr' : '/mo'
  return priceCents === 0 ? 'Free' : `€${amount}${suffix}`
}

const markdownSx = {
  '& p': { m: 0, mb: 0.5 },
  '& ul, & ol': { m: 0, pl: 2.5 },
  '& li': { mb: 0.25 },
  typography: 'body2',
  color: 'text.secondary',
}

const compactMarkdownSx = {
  '& p': { m: 0, mb: 0.25 },
  '& ul, & ol': { m: 0, pl: 2, mb: 0 },
  '& li': { mb: 0, fontSize: '0.75rem' },
  typography: 'caption',
  color: 'text.secondary',
}

interface PlanCardContentProps {
  name: string
  priceCents?: number | null
  billingInterval?: string | null
  description?: string | null
  /** Use smaller typography for compact layouts (e.g. deploy dialog) */
  compact?: boolean
  /** Extra content rendered after the name (e.g. checkmark icon) */
  nameAdornment?: React.ReactNode
  /** Price typography variant */
  priceVariant?: 'h4' | 'h6'
  /** Name typography variant */
  nameVariant?: 'h6' | 'subtitle2'
}

export function PlanCardContent({
  name,
  priceCents,
  billingInterval,
  description,
  compact,
  nameAdornment,
  priceVariant = 'h4',
  nameVariant = 'h6',
}: PlanCardContentProps) {
  const hasTemplate = priceCents != null && billingInterval != null
  const price = hasTemplate ? formatPlanPrice(priceCents, billingInterval) : null

  return (
    <Stack spacing={compact ? 0.5 : 1}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant={nameVariant}>{name || 'Plan name'}</Typography>
        {nameAdornment}
      </Stack>
      {hasTemplate ? (
        <>
          <Typography variant={priceVariant} color="primary" sx={compact ? { mt: 0.25 } : undefined}>
            {price}
          </Typography>
          {description && (
            <Box sx={compact ? compactMarkdownSx : markdownSx}>
              <Markdown>{description}</Markdown>
            </Box>
          )}
        </>
      ) : (
        <>
          <Skeleton variant="text" animation={false} width="60%" sx={{ fontSize: '2.125rem' }} />
          <Skeleton variant="text" animation={false} width="80%" />
          <Skeleton variant="text" animation={false} width="70%" />
          <Skeleton variant="text" animation={false} width="75%" />
        </>
      )}
    </Stack>
  )
}
