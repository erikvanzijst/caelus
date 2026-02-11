export type IsoDate = string

export interface User {
  id: number
  email: string
  created_at: IsoDate
}

export interface Product {
  id: number
  name: string
  description?: string | null
  template_id?: number | null
  created_at: IsoDate
}

export interface ProductTemplate {
  id: number
  docker_image_url?: string | null
  product_id: number
  created_at: IsoDate
  product: Product
}

export interface Deployment {
  id: number
  template_id: number
  domainname: string
  user_id: number
  created_at: IsoDate
  user: User
  template: ProductTemplate
}
