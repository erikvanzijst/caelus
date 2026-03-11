export type IsoDate = string
export type DeploymentStatus = 'provisioning' | 'ready' | 'deleting' | 'deleted' | 'error'

export interface User {
  id: number
  email: string
  is_admin: boolean
  created_at: IsoDate
}

export interface Product {
  id: number
  name: string
  description?: string | null
  template_id?: number | null
  icon_url?: string | null
  created_at: IsoDate
}

export interface ProductTemplate {
  id: number
  product_id: number
  chart_ref: string
  chart_version: string
  chart_digest?: string | null
  version_label?: string | null
  default_values_json?: Record<string, unknown> | null
  values_schema_json?: Record<string, unknown> | null
  capabilities_json?: Record<string, unknown> | null
  created_at: IsoDate
  product: Product
}

export interface Deployment {
  desired_template_id: number
  domainname: string | null
  user_id: number
  user_values_json?: Record<string, unknown> | null
  id: number
  created_at: IsoDate
  user: User
  desired_template: ProductTemplate
  applied_template?: ProductTemplate | null
  deployment_uid?: string | null
  status?: DeploymentStatus
  generation?: number
  last_error?: string | null
  last_reconcile_at?: IsoDate | null
}
