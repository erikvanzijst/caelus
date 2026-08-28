export type IsoDate = string
export type DeploymentStatus = 'pending' | 'provisioning' | 'ready' | 'deleting' | 'deleted' | 'error'

export interface User {
  id: number
  email: string
  is_admin: boolean
  created_at: IsoDate
}

// The current user's Terms of Service acceptance status. `version` is null until
// they have accepted. Sourced from GET /api/me/tos-acceptance.
export interface TosAcceptance {
  version: string | null
  accepted_at: IsoDate | null
}

/** Whether a product is offered to end users ('public') or hidden ('admin'). */
export type ProductVisibility = 'public' | 'admin'

export interface Product {
  id: number
  name: string
  description?: string | null
  template_id?: number | null
  icon_url?: string | null
  category?: string | null
  replaces?: string | null
  visibility: ProductVisibility
  /** Catalog key joining this product to `products/catalog/<slug>.yaml`; null for database-authored products. */
  slug?: string | null
  /** Whether the catalog owns this product. Written only by the reconciler; everything but `visibility` is read-only when true. */
  curated: boolean
  created_at: IsoDate
}

export interface ProductTemplate {
  id: number
  product_id: number
  chart_ref: string
  chart_version: string
  chart_digest?: string | null
  system_values_json?: Record<string, unknown> | null
  values_schema_json?: Record<string, unknown> | null
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
  product_id: number
  template_id?: number | null
  sort_order?: number | null
  created_at: IsoDate
  template?: PlanTemplateVersion | null
}

export interface PlanTemplateVersion {
  id: number
  plan_id: number
  price_cents: number
  billing_interval: 'monthly' | 'annual'
  storage_bytes?: number | null
  database_bytes?: number | null
  description?: string | null
  created_at: IsoDate
  plan?: Plan | null
}

/** The commercial terms accepted when creating a new plan template version. */
export interface PlanTemplatePayload {
  price_cents: number
  billing_interval: string
  storage_bytes?: number | null
  database_bytes?: number | null
  description?: string | null
}

export interface Subscription {
  id: number
  plan_template_id: number
  user_id: number
  status: 'active' | 'cancelled'
  payment_status: 'pending' | 'current' | 'arrears'
  cancelled_at?: IsoDate | null
  created_at: IsoDate
  plan_template?: PlanTemplateVersion | null
}

/**
 * One runtime variable as the API reports it.
 *
 * `value` is **absent** for a sensitive var — not masked, not null. A null
 * would be indistinguishable from the delete gesture, so a client that read a
 * deployment and submitted it back would wipe every secret it could not read.
 */
export interface VarEntry {
  value?: string
  sensitive: boolean
  updated_at: IsoDate
  updated_by: VarWriter
}

export interface VarWriter {
  id: number
  email?: string | null
}

/** One entry in a vars write. Omitting `value` leaves the var unchanged. */
export interface VarWrite {
  value?: string | null
  sensitive?: boolean
}

export interface Deployment {
  desired_template_id: number
  hostname: string | null
  user_id: number
  user_values_json?: Record<string, unknown> | null
  id: string
  created_at: IsoDate
  user: User
  desired_template: ProductTemplate
  applied_template?: ProductTemplate | null
  subscription_id?: number | null
  subscription?: Subscription | null
  name: string
  namespace: string
  status?: DeploymentStatus
  generation?: number
  last_error?: string | null
  last_reconcile_at?: IsoDate | null
  /**
   * The deployment's desired runtime configuration. Present only on a
   * single-deployment read: the listing omits it (`undefined`), which is not
   * the same as a deployment having none (`{}`).
   */
  vars?: Record<string, VarEntry> | null
  /** Whether a rollout would change the running pod's environment. */
  pending?: boolean | null
  applied_release?: DeploymentRelease | null
}

/** The subset of a release this UI reads. */
export interface DeploymentRelease {
  id: string
  number: number
  build_id?: string | null
}

export interface DeploymentCreateResponse {
  deployment: Deployment
  checkout_url: string | null
}

export interface SftpCredentials {
  host: string
  port: number
  username: string
  password: string
}

/**
 * An SSH public key registered on an account. Never carries private key
 * material: none is ever stored or transmitted.
 */
export interface SshKey {
  /** `SHA256:...`, as `ssh-keygen -lf` reports it. Identifies the key. */
  fingerprint: string
  key_type: string
  bits: number
  label: string | null
  /** Normalized `<type> <blob>`; the comment lives in `label` instead. */
  public_key: string
  created_at: IsoDate
}
