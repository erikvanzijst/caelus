import { requestJson, requestMultipart } from './client'
import type { Deployment, HostnameCheckResult, Product, ProductTemplate, User } from './types'

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

export function listDeployments(userId: number) {
  return requestJson<Deployment[]>(`/users/${userId}/deployments`)
}

export function createDeployment(
  userId: number,
  payload: { desired_template_id: number; user_values_json?: object },
) {
  return requestJson<Deployment>(`/users/${userId}/deployments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateDeployment(
  userId: number,
  deploymentId: number,
  payload: { desired_template_id: number; user_values_json?: object },
) {
  return requestJson<Deployment>(`/users/${userId}/deployments/${deploymentId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteDeployment(userId: number, deploymentId: number) {
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
