## Context

Caelus currently lacks built-in authentication, relying on an external auth provider to set the `X-Auth-Request-Email` header. The goal is to deploy Keycloak (identity provider) and oauth2-proxy (authentication proxy) in front of Caelus on the existing Kubernetes cluster using the existing Terraform project.

**Current State:**
- Caelus receives requests with `X-Auth-Request-Email` header from upstream proxy
- No local user management or registration capability
- No social authentication options

**Constraints:**
- Use existing Kubernetes cluster configured in `./tf/`
- No TLS (handled by external load balancer)
- SMTP server available for Keycloak verification emails
- Must maintain `X-Auth-Request-Email` header for Caelus

## Goals / Non-Goals

**Goals:**
- Deploy Keycloak on Kubernetes for identity management
- Deploy oauth2-proxy as authentication gateway in front of Caelus
- Enable local user registration with email validation
- Enable social auth: Google, Apple, Microsoft
- Forward authenticated user email to Caelus via `X-Auth-Request-Email` header

**Non-Goals:**
- Database changes to Caelus (no user table modifications)
- Caelus code changes (relies on auth header)
- TLS/certificate management (external LB handles this)
- Multi-factor authentication (MFA) setup
- Custom Keycloak themes or branding

## Decisions

### Decision 1: Keycloak Deployment Approach
**Chosen:** Deploy Keycloak via Kubernetes Deployment with embedded H2 database for simplicity  
**Rationale:** H2 is suitable for development/small deployments. For production, can migrate to external PostgreSQL later without code changes.

**Alternative Considered:** Use Keycloak Operator - More complex, adds operational burden for initial setup.

### Decision 2: oauth2-proxy vs. Keycloak Gatekeeper
**Chosen:** oauth2-proxy  
**Rationale:** oauth2-proxy is widely used, well-documented, and specifically designed to sit in front of applications and inject auth headers. Keycloak Gatekeeper is deprecated in favor of oauth2-proxy.

**Alternative Considered:** Keycloak Gatekeeper (deprecated), mod_auth_openidc (Apache/nginx module)

### Decision 3: OAuth Flow
**Chosen:** Authorization Code Flow with PKCE  
**Rationale:** Most secure for web/mobile apps, recommended by OAuth 2.1.

**Alternative Considered:** Implicit Flow - Deprecated, less secure.

### Decision 4: Terraform Structure
**Chosen:** Add new modules under `./tf/` for keycloak and oauth2-proxy  
**Rationale:** Follows existing Terraform patterns, keeps infrastructure as code consistent.

### Decision 5: Ingress Configuration
**Chosen:** Separate Ingress resources for Keycloak (admin) and oauth2-proxy (app access)  
**Rationale:** Keycloak needs separate URL for admin console, oauth2-proxy handles app traffic.

## Risks / Trade-offs

- **[Risk]** Keycloak H2 database persistence → **Mitigation:** Use PVC for persistence, plan for PostgreSQL migration if scaling
- **[Risk]** Session management between oauth2-proxy and Keycloak → **Mitigation:** Use Redis for oauth2-proxy sessions if high availability needed
- **[Risk]** Social provider credential management → **Mitigation:** Store in Kubernetes Secrets, rotate regularly
- **[Risk]** Keycloak startup time → **Mitigation:** Configure readiness/liveness probes appropriately

## Migration Plan

1. **Phase 1: Infrastructure Setup**
   - Add Keycloak Kubernetes manifests to Terraform
   - Add oauth2-proxy Kubernetes manifests to Terraform
   - Create Kubernetes namespace (e.g., `auth-system`)
   - Apply Terraform changes

2. **Phase 2: Configuration**
   - Configure Keycloak realm with local user registration enabled
   - Configure SMTP settings for email validation
   - Set up social identity providers (Google, Apple, Microsoft)
   - Configure oauth2-proxy to use Keycloak as OIDC provider

3. **Phase 3: Integration**
   - Update Caelus Ingress to route through oauth2-proxy
   - Verify `X-Auth-Request-Email` header is forwarded correctly
   - Test local registration flow
   - Test social login flows

4. **Phase 4: Cutover**
   - Switch production traffic to oauth2-proxy
   - Monitor authentication flows
   - Decommission any legacy auth proxies

## Open Questions

- Should Keycloak use an external PostgreSQL database instead of H2?
- What subdomain strategy? (e.g., `auth.example.com` for Keycloak, `app.example.com` for Caelus)
- Need to configure email from address for Keycloak SMTP?
