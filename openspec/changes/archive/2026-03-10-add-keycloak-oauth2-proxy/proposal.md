## Why

Caelus currently lacks built-in authentication, relying on external systems to provide user identity via the `X-Auth-Request-Email` header. We need to implement a complete authentication layer with Keycloak and oauth2-proxy to provide secure access control, local user registration with email validation, and social login providers (Google, Apple, Microsoft).

## What Changes

- Deploy Keycloak containerized on Kubernetes for identity management
- Deploy oauth2-proxy as the authentication reverse proxy in front of Caelus
- Configure Keycloak with local user registration and email validation
- Add social identity providers: Google, Apple, Microsoft
- Configure oauth2-proxy to extract user email and forward as `X-Auth-Request-Email` header to Caelus
- Use existing Terraform project (`./tf/`) for all Kubernetes deployments
- Update Caelus to trust authenticated requests from oauth2-proxy (noting that we're using Traefik as the ingress controller)

## Capabilities

### New Capabilities
- `keycloak-deployment`: Deploy and configure Keycloak on Kubernetes
- `oauth2-proxy-deployment`: Deploy oauth2-proxy as authentication gateway
- `keycloak-user-realm`: Configure Keycloak realm with local users and social providers
- `auth-header-integration`: Ensure X-Auth-Request-Email header is properly forwarded to Caelus

### Modified Capabilities
- (none - no existing authentication specs to modify)

## Impact

- New infrastructure components: Keycloak, oauth2-proxy
- Terraform: New modules/configurations in `./tf/`
- Kubernetes: New Deployments, Services, Ingress resources
- Caelus: No code changes needed, relies on auth header
