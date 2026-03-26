import { requestJson, requestMultipart } from './client'
import type { Deployment, DeploymentCreateResponse, HostnameCheckResult, Plan, PlanTemplateVersion, Product, ProductTemplate, User } from './types'

export function getMe() {
  return requestJson<User>('/me')
}

export function listUsers() {
  return requestJson<User[]>('/users')
}

export function createUser(email: string) {
  return requestJson<User>('/users', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function listProducts() {
  return requestJson<Product[]>('/products')
}

export function createProduct(
  payload: { name: string; description?: string | null },
  iconFile?: File,
) {
  if (iconFile) {
    return requestMultipart<Product>('/products', payload, { field: 'icon', file: iconFile })
  }
  return requestJson<Product>('/products', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteProduct(productId: number) {
  return requestJson<null>(`/products/${productId}`, { method: 'DELETE' })
}

export function updateProduct(
  productId: number,
  payload: { name?: string; description?: string | null; template_id?: number },
  iconFile?: File,
) {
  if (iconFile) {
    return requestMultipart<Product>(
      `/products/${productId}`,
      payload,
      { field: 'icon', file: iconFile },
      {},
      'PUT',
    )
  }
  return requestJson<Product>(`/products/${productId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function updateProductTemplate(productId: number, templateId: number) {
  return updateProduct(productId, { template_id: templateId })
}

export function listTemplates(productId: number) {
  return requestJson<ProductTemplate[]>(`/products/${productId}/templates`)
}

export function createTemplate(
  productId: number,
  payload: { chart_ref: string; chart_version: string; values_schema_json?: object; system_values_json?: object },
) {
  return requestJson<ProductTemplate>(`/products/${productId}/templates`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteTemplate(productId: number, templateId: number) {
  return requestJson<null>(`/products/${productId}/templates/${templateId}`, {
    method: 'DELETE',
  })
}

export function listPlans(productId: number) {
  return requestJson<Plan[]>(`/products/${productId}/plans`)
}

export function createPlan(productId: number, payload: { name: string; sort_order?: number | null }) {
  return requestJson<Plan>(`/products/${productId}/plans`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updatePlan(planId: number, payload: { name?: string; template_id?: number; sort_order?: number | null }) {
  return requestJson<Plan>(`/plans/${planId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deletePlan(planId: number) {
  return requestJson<null>(`/plans/${planId}`, { method: 'DELETE' })
}

export function listPlanTemplates(planId: number) {
  return requestJson<PlanTemplateVersion[]>(`/plans/${planId}/templates`)
}

export function createPlanTemplate(planId: number, payload: { price_cents: number; billing_interval: string; storage_bytes?: number | null; description?: string | null }) {
  return requestJson<PlanTemplateVersion>(`/plans/${planId}/templates`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listAllDeployments() {
  return requestJson<Deployment[]>('/deployments')
}

export function getDeployment(userId: number, deploymentId: string) {
  return requestJson<Deployment>(`/users/${userId}/deployments/${deploymentId}`)
}

export function listDeployments(userId: number) {
  return requestJson<Deployment[]>(`/users/${userId}/deployments`)
}

export function createDeployment(
  userId: number,
  payload: { desired_template_id: number; user_values_json?: object; plan_template_id?: number },
) {
  return requestJson<DeploymentCreateResponse>(`/users/${userId}/deployments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateDeployment(
  userId: number,
  deploymentId: string,
  payload: { desired_template_id: number; user_values_json?: object },
) {
  return requestJson<Deployment>(`/users/${userId}/deployments/${deploymentId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteDeployment(userId: number, deploymentId: string) {
  return requestJson<null>(`/users/${userId}/deployments/${deploymentId}`, {
    method: 'DELETE',
  })
}

export function checkHostname(fqdn: string) {
  return requestJson<HostnameCheckResult>(`/hostnames/${encodeURIComponent(fqdn)}`)
}

export function listDomains() {
  return requestJson<string[]>('/domains')
}
