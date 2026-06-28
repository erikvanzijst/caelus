import { useQuery } from '@tanstack/react-query'
import { listProducts } from '../../api/endpoints'

/** Demo/internal products that should never appear on the public landing page. */
export const EXCLUDED_PRODUCTS = new Set(['hello world', 'naas'])

export interface ProductSummary {
  id: number
  name: string
  description?: string | null
  iconUrl?: string | null
  category?: string | null
  replaces?: string | null
}

/** Fetch the public-facing products (excluding demos), preserving API order. */
export async function loadVisibleProducts(): Promise<ProductSummary[]> {
  const products = await listProducts()
  return products
    .filter((product) => !EXCLUDED_PRODUCTS.has(product.name.trim().toLowerCase()))
    .map((product) => ({
      id: product.id,
      name: product.name,
      description: product.description,
      iconUrl: product.icon_url,
      category: product.category,
      replaces: product.replaces,
    }))
}

/** Cached query of the products shown across the landing page. */
export function useLandingProducts() {
  return useQuery({
    queryKey: ['landing-products'],
    queryFn: loadVisibleProducts,
    staleTime: 5 * 60 * 1000,
  })
}

export default useLandingProducts
