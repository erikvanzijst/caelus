import { requestJson } from './client'
import type { Deployment, Product, ProductTemplate, User } from './types'

export function listUsers(authEmail?: string) {
  return requestJson<User[]>('/users', { authEmail })
}

export function createUser(email: string, authEmail?: string) {
  return requestJson<User>('/users', {
    method: 'POST',
    body: JSON.stringify({ email }),
    authEmail,
  })
}

export function listProducts(authEmail?: string) {
  return requestJson<Product[]>('/products', { authEmail })
}

export function createProduct(payload: { name: string; description?: string | null }, authEmail?: string) {
  return requestJson<Product>('/products', {
    method: 'POST',
    body: JSON.stringify(payload),
    authEmail,
  })
}

export function deleteProduct(productId: number, authEmail?: string) {
  return requestJson<null>(`/products/${productId}`, { method: 'DELETE', authEmail })
}

export function updateProductTemplate(productId: number, templateId: number, authEmail?: string) {
  return requestJson<Product>(`/products/${productId}`, {
    method: 'PUT',
    body: JSON.stringify({ template_id: templateId }),
    authEmail,
  })
}

export function listTemplates(productId: number, authEmail?: string) {
  return requestJson<ProductTemplate[]>(`/products/${productId}/templates`, { authEmail })
}

export function createTemplate(
  productId: number,
  payload: { docker_image_url?: string | null },
  authEmail?: string,
) {
  return requestJson<ProductTemplate>(`/products/${productId}/templates`, {
    method: 'POST',
    body: JSON.stringify(payload),
    authEmail,
  })
}

export function deleteTemplate(productId: number, templateId: number, authEmail?: string) {
  return requestJson<null>(`/products/${productId}/templates/${templateId}`, {
    method: 'DELETE',
    authEmail,
  })
}

export function listDeployments(userId: number, authEmail?: string) {
  return requestJson<Deployment[]>(`/users/${userId}/deployments`, { authEmail })
}

export function createDeployment(
  userId: number,
  payload: { template_id: number; domainname: string },
  authEmail?: string,
) {
  return requestJson<Deployment>(`/users/${userId}/deployments`, {
    method: 'POST',
    body: JSON.stringify(payload),
    authEmail,
  })
}

export function deleteDeployment(userId: number, deploymentId: number, authEmail?: string) {
  return requestJson<null>(`/users/${userId}/deployments/${deploymentId}`, {
    method: 'DELETE',
    authEmail,
  })
}
