import {
  Avatar,
  Box,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography,
} from '@mui/material'
import { resolveApiPath } from '../api/client'
import type { Product } from '../api/types'

interface ProductListProps {
  products?: Product[]
  selectedProductId: number | null
  onSelectProduct: (productId: number) => void
}

export function ProductList({ products, selectedProductId, onSelectProduct }: ProductListProps) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6">Products</Typography>
          {products?.map((product) => (
            <Box
              key={product.id}
              onClick={() => onSelectProduct(product.id)}
              sx={{
                p: 2,
                borderRadius: 2,
                border: '1px solid rgba(148, 163, 184, 0.2)',
                cursor: 'pointer',
                bgcolor:
                  selectedProductId === product.id ? 'rgba(37,99,235,0.08)' : 'transparent',
              }}
            >
              <Stack direction="row" spacing={1.5} alignItems="center">
                <Avatar
                  src={product.icon_url ? resolveApiPath(product.icon_url) : undefined}
                  alt={product.name}
                  sx={{ width: 36, height: 36 }}
                >
                  {product.name[0]}
                </Avatar>
                <Stack spacing={0.5} sx={{ minWidth: 0 }}>
                  <Typography variant="subtitle1">{product.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {product.description || 'No description'}
                  </Typography>
                  <Chip
                    label={
                      product.template_id
                        ? `Canonical template #${product.template_id}`
                        : 'No canonical template'
                    }
                    size="small"
                    color={product.template_id ? 'primary' : 'default'}
                    variant="outlined"
                    sx={{ alignSelf: 'flex-start' }}
                  />
                </Stack>
              </Stack>
            </Box>
          ))}
        </Stack>
      </CardContent>
    </Card>
  )
}
