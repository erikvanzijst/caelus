import { Card, CardContent } from '@mui/material'
import { PlanCardContent } from './PlanCardContent'

interface PlanCardPreviewProps {
  name: string
  priceCents?: number | null
  billingInterval?: string | null
  description?: string | null
}

export function PlanCardPreview({ name, priceCents, billingInterval, description }: PlanCardPreviewProps) {
  return (
    <Card variant="outlined" sx={{ maxWidth: 300 }}>
      <CardContent>
        <PlanCardContent
          name={name}
          priceCents={priceCents}
          billingInterval={billingInterval}
          description={description}
        />
      </CardContent>
    </Card>
  )
}
