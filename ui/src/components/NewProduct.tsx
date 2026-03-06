import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Box, Button, Card, CardActions, CardContent, Stack, TextField, Typography } from '@mui/material'
import { createProduct } from '../api/endpoints'
import { IconInput } from './IconInput'

interface NewProductProps {
  authEmail?: string
  onSuccess: () => void
  onError: (error: Error) => void
}

export function NewProduct({ authEmail, onSuccess, onError }: NewProductProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [iconFile, setIconFile] = useState<File | null>(null)

  const createProductMutation = useMutation({
    mutationFn: () =>
      createProduct(
        {
          name: name.trim(),
          description: description.trim() || null,
        },
        authEmail,
        iconFile || undefined,
      ),
    onSuccess: () => {
      setName('')
      setDescription('')
      setIconFile(null)
      onSuccess()
    },
    onError,
  })

  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6">Create product</Typography>
          <TextField
            label="Product name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <TextField
            label="Description"
            multiline
            minRows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Product icon (optional)
            </Typography>
            <IconInput value={iconFile} onChange={setIconFile} />
          </Box>
        </Stack>
      </CardContent>
      <CardActions sx={{ px: 2, pb: 2 }}>
        <Button
          variant="contained"
          disabled={!name.trim() || createProductMutation.isPending}
          onClick={() => createProductMutation.mutate()}
        >
          Add product
        </Button>
      </CardActions>
    </Card>
  )
}
