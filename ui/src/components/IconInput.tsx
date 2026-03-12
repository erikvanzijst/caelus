import { useCallback, useEffect, useRef, useState } from 'react'
import { Box, Button, Typography } from '@mui/material'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'

interface IconInputProps {
  value: File | null
  onChange: (file: File | null) => void
  inputId?: string
}

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
const MAX_IMAGE_DIMENSION = 2048

async function loadImageFromUrl(url: string): Promise<HTMLImageElement> {
  return await new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('Could not load image'))
    image.src = url
  })
}

async function scaleImageFile(file: File): Promise<File> {
  const objectUrl = URL.createObjectURL(file)
  try {
    const image = await loadImageFromUrl(objectUrl)
    const scale = Math.min(
      1,
      MAX_IMAGE_DIMENSION / image.naturalWidth,
      MAX_IMAGE_DIMENSION / image.naturalHeight,
    )

    if (scale >= 1) {
      return file
    }

    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.floor(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.floor(image.naturalHeight * scale))

    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('Could not process image')
    }

    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) {
          resolve(result)
          return
        }
        reject(new Error('Could not process image'))
      }, 'image/png')
    })

    return new File([blob], 'icon.png', { type: 'image/png' })
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

export function IconInput({ value, onChange, inputId = 'icon-input' }: IconInputProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!value) {
      setPreviewUrl(null)
      return
    }

    const url = URL.createObjectURL(value)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [value])

  const handleFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (!file) return

      setError(null)

      if (!file.type.startsWith('image/')) {
        setError('Please select an image file')
        return
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        setError('File size must be less than 10MB')
        return
      }

      try {
        const processed = await scaleImageFile(file)
        onChange(processed)
      } catch {
        setError('Could not process image')
      }
    },
    [onChange],
  )

  const handleClear = useCallback(() => {
    setError(null)
    onChange(null)
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }, [onChange])

  return (
    <Box>
      <input
        ref={inputRef}
        accept="image/*"
        style={{ display: 'none' }}
        id={inputId}
        type="file"
        onChange={handleFileChange}
      />
      <label htmlFor={inputId}>
        <Button variant="outlined" component="span" startIcon={<CloudUploadIcon />}>
          Choose icon
        </Button>
      </label>

      {error && (
        <Typography sx={{ mt: 1 }} variant="body2" color="error">
          {error}
        </Typography>
      )}

      {previewUrl && (
        <Box sx={{ mt: 2 }}>
          <img src={previewUrl} alt="Icon preview" style={{ maxWidth: '100%', maxHeight: 300 }} />
          <Box sx={{ mt: 1, display: 'flex', gap: 1 }}>
            <Button variant="outlined" size="small" onClick={handleClear}>
              Clear
            </Button>
          </Box>
        </Box>
      )}
    </Box>
  )
}
