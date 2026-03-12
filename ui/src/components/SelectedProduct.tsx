import { useState } from 'react'
import {
  Avatar,
  Button,
  Card,
  CardActions,
  CardContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { deleteProduct, updateProduct } from '../api/endpoints'
import { resolveApiPath } from '../api/client'
import type { Product } from '../api/types'
import { formatDateTime } from '../utils/format'

interface SelectedProductProps {
  product?: Product
  onError: (error: Error) => void
}

export function SelectedProduct({ product, onError }: SelectedProductProps) {
  const queryClient = useQueryClient()
  const [editingName, setEditingName] = useState(false)
  const [editingDesc, setEditingDesc] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [draftDesc, setDraftDesc] = useState('')

  const updateProductMutation = useMutation({
    mutationFn: (payload: { name?: string; description?: string | null }) =>
      updateProduct(product!.id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
    onError,
  })

  const deleteProductMutation = useMutation({
    mutationFn: () => deleteProduct(product!.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
    onError,
  })

  function saveName() {
    const trimmed = draftName.trim()
    if (trimmed && trimmed !== product?.name) {
      updateProductMutation.mutate({ name: trimmed })
    }
    setEditingName(false)
  }

  function saveDescription() {
    const trimmed = draftDesc.trim()
    if (trimmed !== (product?.description ?? '')) {
      updateProductMutation.mutate({ description: trimmed || null })
    }
    setEditingDesc(false)
  }

  return (
    <Card>
      <CardContent>
        <Stack spacing={1}>
          <Typography variant="h6">Selected product</Typography>
          <Stack direction="row" spacing={2} alignItems="center">
            <Avatar
              src={product?.icon_url ? resolveApiPath(product.icon_url) : undefined}
              alt={product?.name}
              sx={{ width: 56, height: 56 }}
            >
              {product?.name?.[0] ?? '?'}
            </Avatar>
            <Stack spacing={0.5} sx={{ minWidth: 0, flex: 1 }}>
              {editingName ? (
                <TextField
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  onBlur={saveName}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveName()
                    if (e.key === 'Escape') setEditingName(false)
                  }}
                  variant="standard"
                  autoFocus
                  slotProps={{ input: { sx: { fontSize: '1.5rem', fontWeight: 500 } } }}
                />
              ) : (
                <Typography
                  variant="h5"
                  onClick={() => {
                    if (!product) return
                    setDraftName(product.name)
                    setEditingName(true)
                  }}
                  sx={{ cursor: product ? 'pointer' : 'default', '&:hover': product ? { color: 'primary.main' } : {} }}
                >
                  {product?.name ?? 'Pick a product'}
                </Typography>
              )}
              {editingDesc ? (
                <TextField
                  value={draftDesc}
                  onChange={(e) => setDraftDesc(e.target.value)}
                  onBlur={saveDescription}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) saveDescription()
                    if (e.key === 'Escape') setEditingDesc(false)
                  }}
                  variant="standard"
                  autoFocus
                  multiline
                  placeholder="No description provided."
                />
              ) : (
                <Typography
                  color="text.secondary"
                  onClick={() => {
                    if (!product) return
                    setDraftDesc(product.description ?? '')
                    setEditingDesc(true)
                  }}
                  sx={{ cursor: product ? 'pointer' : 'default', '&:hover': product ? { color: 'primary.main' } : {} }}
                >
                  {product?.description || 'No description provided.'}
                </Typography>
              )}
              <Typography variant="body2" color="text.secondary">
                Created {formatDateTime(product?.created_at)}
              </Typography>
            </Stack>
          </Stack>
        </Stack>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Button
          variant="outlined"
          color="secondary"
          disabled={!product}
          onClick={() => {
            if (!product) return
            if (window.confirm(`Delete ${product.name}?`)) {
              deleteProductMutation.mutate()
            }
          }}
        >
          Delete product
        </Button>
      </CardActions>
    </Card>
  )
}
