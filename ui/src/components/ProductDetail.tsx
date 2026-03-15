import { Card, Divider } from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import { listTemplates } from '../api/endpoints'
import type { Product } from '../api/types'
import { SelectedProduct } from './SelectedProduct'
import { TemplateTabs } from './TemplateTabs'

interface ProductDetailProps {
  product: Product
  onError: (error: Error) => void
}

export function ProductDetail({ product, onError }: ProductDetailProps) {
  const templatesQuery = useQuery({
    queryKey: ['templates', product.id],
    queryFn: () => listTemplates(product.id),
  })

  return (
    <Card>
      <SelectedProduct product={product} onError={onError} />
      <Divider />
      <TemplateTabs
        product={product}
        templates={templatesQuery.data ?? []}
        onError={onError}
      />
    </Card>
  )
}
