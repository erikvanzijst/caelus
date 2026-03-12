import {
  Avatar,
  Box,
  Card,
  CardActionArea,
  CardContent,
  Grid,
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
    <Grid container spacing={2}>
      {products?.map((product) => (
        <Grid key={product.id} size={{ xs: 6, sm: 4, md: 3 }}>
          <Card
            sx={{
              height: '100%',
              border: selectedProductId === product.id
                ? '2px solid'
                : '2px solid transparent',
              borderColor: selectedProductId === product.id
                ? 'primary.main'
                : 'transparent',
            }}
          >
            <CardActionArea
              onClick={() => onSelectProduct(product.id)}
              sx={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
            >
              <CardContent sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 1 }}>
                <Avatar
                  src={product.icon_url ? resolveApiPath(product.icon_url) : undefined}
                  alt={product.name}
                  variant="rounded"
                  sx={{ width: 48, height: 48 }}
                >
                  {product.name[0]}
                </Avatar>
                <Box sx={{ minWidth: 0, width: '100%' }}>
                  <Typography variant="subtitle2" noWrap>{product.name}</Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {product.description || 'No description'}
                  </Typography>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
      ))}
    </Grid>
  )
}
