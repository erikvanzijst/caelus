import { Box, Card, CardContent, Skeleton, Stack, Typography } from '@mui/material'
import Markdown from 'react-markdown'

function formatPrice(priceCents: number, interval: string): string {
  const amount = (priceCents / 100).toFixed(priceCents % 100 === 0 ? 0 : 2)
  const suffix = interval === 'annual' ? '/yr' : '/mo'
  return priceCents === 0 ? 'Free' : `€${amount}${suffix}`
}

interface PlanCardPreviewProps {
  name: string
  priceCents?: number | null
  billingInterval?: string | null
  description?: string | null
}

export function PlanCardPreview({ name, priceCents, billingInterval, description }: PlanCardPreviewProps) {
  const hasTemplate = priceCents != null && billingInterval != null
  const price = hasTemplate ? formatPrice(priceCents, billingInterval) : null

  return (
    <Card variant="outlined" sx={{ maxWidth: 300 }}>
      <CardContent>
        <Stack spacing={1}>
          <Typography variant="h6">{name || 'Plan name'}</Typography>
          {hasTemplate ? (
            <Typography variant="h4" color="primary">{price}</Typography>
          ) : (
            <Skeleton variant="text" animation={false} width="60%" sx={{ fontSize: '2.125rem' }} />
          )}
          {hasTemplate && description ? (
            <Box
              sx={{
                '& p': { m: 0, mb: 0.5 },
                '& ul, & ol': { m: 0, pl: 2.5 },
                '& li': { mb: 0.25 },
                typography: 'body2',
                color: 'text.secondary',
              }}
            >
              <Markdown>{description}</Markdown>
            </Box>
          ) : !hasTemplate ? (
            <>
              <Skeleton variant="text" animation={false} width="80%" />
              <Skeleton variant="text" animation={false} width="70%" />
              <Skeleton variant="text" animation={false} width="75%" />
            </>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  )
}
