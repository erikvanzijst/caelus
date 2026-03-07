## 1. Terraform Infrastructure Setup

- [ ] 1.1 Create `auth-system` namespace in Terraform (or add to existing namespace.tf)
- [ ] 1.2 Create Keycloak Kubernetes manifest resources in Terraform
  - [ ] 1.2.1 Deployment with H2 database
  - [ ] 1.2.2 Service (ClusterIP)
  - [ ] 1.2.3 PersistentVolumeClaim for data persistence
  - [ ] 1.2.4 Ingress for Keycloak admin/realm access
- [ ] 1.3 Create oauth2-proxy Kubernetes manifest resources in Terraform
  - [ ] 1.3.1 Deployment with OIDC configuration
  - [ ] 1.3.2 Service (ClusterIP)
  - [ ] 1.3.3 Ingress for Caelus access
- [ ] 1.4 Create Kubernetes Secrets for oauth2-proxy in Terraform
  - [ ] 1.4.1 OAuth client secret
  - [ ] 1.4.2 Cookie secret
- [ ] 1.5 Create ConfigMaps for oauth2-proxy configuration in Terraform

## 2. Keycloak Configuration

- [ ] 2.1 Create `caelus` realm in Keycloak
- [ ] 2.2 Enable local user registration
- [ ] 2.3 Enable email verification requirement
- [ ] 2.4 Configure SMTP settings for email sending
- [ ] 2.5 Configure Google identity provider
  - [ ] 2.5.1 Create OAuth client in Google Cloud
  - [ ] 2.5.2 Add Google IDP in Keycloak with client ID/secret
- [ ] 2.6 Configure Apple identity provider
  - [ ] 2.6.1 Create OAuth app in Apple Developer
  - [ ] 2.6.2 Add Apple IDP in Keycloak with credentials
- [ ] 2.7 Configure Microsoft identity provider
  - [ ] 2.7.1 Create Azure AD app registration
  - [ ] 2.7.2 Add Microsoft IDP in Keycloak with tenant/client ID/secret
- [ ] 2.8 Create oauth2-proxy client in Keycloak
  - [ ] 2.8.1 Set client ID to `oauth2-proxy`
  - [ ] 2.8.2 Configure valid redirect URIs
  - [ ] 2.8.3 Enable authorization code flow with PKCE

## 3. oauth2-proxy Configuration

- [ ] 3.1 Configure OIDC issuer URL (Keycloak realm URL)
- [ ] 3.2 Configure client ID and secret
- [ ] 3.3 Set up cookie secret
- [ ] 3.4 Configure email domain/claim mapping
- [ ] 3.5 Enable X-Auth-Request headers (SET_XAUTHREQUEST)
- [ ] 3.6 Configure upstream to Caelus service
- [ ] 3.7 Configure session handling
- [ ] 3.8 Set up health check endpoints

## 4. Caelus Ingress Integration

- [ ] 4.1 Update Caelus Ingress to route through oauth2-proxy
- [ ] 4.2 Verify X-Auth-Request-Email header is forwarded
- [ ] 4.3 Test unauthenticated request redirect behavior

## 5. Testing & Validation

- [ ] 5.1 Test local user registration flow
  - [ ] 5.1.1 Register new user
  - [ ] 5.1.2 Verify email is sent
  - [ ] 5.1.3 Verify email validation link works
- [ ] 5.2 Test Google social login
- [ ] 5.3 Test Apple social login
- [ ] 5.4 Test Microsoft social login
- [ ] 5.5 Verify X-Auth-Request-Email header reaches Caelus
- [ ] 5.6 Test authenticated access to Caelus
- [ ] 5.7 Test unauthenticated access redirects to login
