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
  system_values_json?: Record<string, unknown> | null
  values_schema_json?: Record<string, unknown> | null
  capabilities_json?: Record<string, unknown> | null
  created_at: IsoDate
  product: Product
}

export interface HostnameCheckResult {
  fqdn: string
  usable: boolean
  reason: string | null
}

export interface Plan {
  id: number
  name: string
  description?: string | null
  product_id: number
  template_id?: number | null
  sort_order?: number | null
  created_at: IsoDate
}

export interface PlanTemplateVersion {
  id: number
  plan_id: number
  price_cents: number
  billing_interval: 'monthly' | 'annual'
  storage_bytes?: number | null
  created_at: IsoDate
  plan?: Plan | null
}

export interface Subscription {
  id: number
  plan_template_id: number
  user_id: number
  status: 'active' | 'cancelled'
  payment_status: 'current' | 'arrears'
  cancelled_at?: IsoDate | null
  external_ref?: string | null
  created_at: IsoDate
  plan_template?: PlanTemplateVersion | null
}

export interface Deployment {
  desired_template_id: number
  hostname: string | null
  user_id: number
  user_values_json?: Record<string, unknown> | null
  id: number
  created_at: IsoDate
  user: User
  desired_template: ProductTemplate
  applied_template?: ProductTemplate | null
  subscription_id?: number | null
  subscription?: Subscription | null
  name?: string | null
  namespace?: string | null
  status?: DeploymentStatus
  generation?: number
  last_error?: string | null
  last_reconcile_at?: IsoDate | null
}
