## 1. Terraform Infrastructure Setup

- [x] 1.1 Create `auth-system` namespace in Terraform
- [x] 1.2 Deploy Keycloak using Bitnami Helm chart
- [x] 1.3 Deploy oauth2-proxy using official Helm chart
- [x] 1.4 Create Kubernetes Secrets for oauth2-proxy in Terraform
  - [x] 1.4.1 OAuth client secret
  - [x] 1.4.2 Cookie secret
- [x] 1.5 Configure Ingress for Keycloak and oauth2-proxy

## 2. Keycloak Configuration

- [x] 2.1 Create `caelus` realm in Keycloak (via keycloakConfigCli)
- [x] 2.2 Enable local user registration (via keycloakConfigCli)
- [x] 2.3 Enable email verification requirement (via keycloakConfigCli)
- [x] 2.4 Configure SMTP settings for email sending (via keycloakConfigCli)
- [ ] 2.5 Configure Google identity provider (manual - requires GCP credentials)
- [ ] 2.5.1 Create OAuth client in Google Cloud
- [ ] 2.5.2 Add Google IDP in Keycloak with client ID/secret
- [ ] 2.6 Configure Apple identity provider (manual - requires Apple Developer account)
- [ ] 2.6.1 Create OAuth app in Apple Developer
- [ ] 2.6.2 Add Apple IDP in Keycloak with credentials
- [ ] 2.7 Configure Microsoft identity provider (manual - requires Azure AD)
- [ ] 2.7.1 Create Azure AD app registration
- [ ] 2.7.2 Add Microsoft IDP in Keycloak with tenant/client ID/secret
- [x] 2.8 Create oauth2-proxy client in Keycloak (via keycloakConfigCli)
  - [x] 2.8.1 Set client ID to `oauth2-proxy`
  - [x] 2.8.2 Configure valid redirect URIs
  - [x] 2.8.3 Enable authorization code flow with PKCE

## 3. oauth2-proxy Configuration

- [x] 3.1 Configure OIDC issuer URL (Keycloak realm URL)
- [x] 3.2 Configure client ID and secret
- [x] 3.3 Set up cookie secret
- [x] 3.4 Configure email domain/claim mapping
- [x] 3.5 Enable X-Auth-Request headers (SET_XAUTHREQUEST)
- [x] 3.6 Configure upstream to Caelus service
- [x] 3.7 Configure session handling
- [x] 3.8 Set up health check endpoints

## 4. Caelus Ingress Integration

- [x] 4.1 Update Caelus Ingress to route through oauth2-proxy
- [x] 4.2 Verify X-Auth-Request-Email header is forwarded
- [x] 4.3 Test unauthenticated request redirect behavior

## 5. Testing & Validation

- [x] 5.1 Test local user registration flow
  - [x] 5.1.1 Register new user
  - [x] 5.1.2 Verify email is sent
  - [x] 5.1.3 Verify email validation link works
- [ ] 5.2 Test Google social login
- [ ] 5.3 Test Apple social login
- [ ] 5.4 Test Microsoft social login
- [ ] 5.5 Verify X-Auth-Request-Email header reaches Caelus
- [x] 5.6 Test authenticated access to Caelus
- [x] 5.7 Test unauthenticated access redirects to login
