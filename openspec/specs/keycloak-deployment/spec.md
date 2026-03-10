# keycloak-deployment Specification

## Purpose
Deploy Keycloak identity provider on Kubernetes for user authentication.

## ADDED Requirements

### Requirement: Keycloak runs on Kubernetes
The system SHALL deploy Keycloak as a Kubernetes Deployment with embedded H2 database.

#### Scenario: Keycloak deployment exists
- **WHEN** `kubectl get deployment -n auth-system keycloak` is executed
- **THEN** a deployment named `keycloak` exists in the `auth-system` namespace

#### Scenario: Keycloak pod is running
- **WHEN** `kubectl get pods -n auth-system -l app=keycloak` is executed
- **THEN** at least one pod shows status `Running`

#### Scenario: Keycloak service is exposed
- **WHEN** `kubectl get svc -n auth-system keycloak` is executed
- **THEN** a ClusterIP service exposes port 8080

### Requirement: Keycloak data persists across restarts
The system SHALL use a PersistentVolumeClaim to persist Keycloak data.

#### Scenario: PVC exists for Keycloak
- **WHEN** `kubectl get pvc -n auth-system keycloak-data` is executed
- **THEN** a PVC exists and is bound

### Requirement: Keycloak is reachable via Ingress
The system SHALL expose Keycloak via Kubernetes Ingress for external access.

#### Scenario: Keycloak Ingress exists
- **WHEN** `kubectl get ingress -n auth-system keycloak` is executed
- **THEN** an Ingress resource exists pointing to keycloak service

### Requirement: Keycloak is configured via environment variables
The system SHALL configure Keycloak with required environment variables including hostname, realm, and OIDC settings.

#### Scenario: Keycloak environment variables are set
- **WHEN** Keycloak pod spec is inspected
- **THEN** environment variables include `KC_HOSTNAME`, `KC_HTTP_ENABLED`, and `KC_DB`

### Requirement: Keycloak has health checks
The system SHALL configure readiness and liveness probes for Keycloak.

#### Scenario: Keycloak probes are configured
- **WHEN** Keycloak deployment spec is inspected
- **THEN** both readinessProbe and livenessProbe are defined

### Requirement: Keycloak resources are managed by Terraform
The system SHALL provision all Kubernetes resources via Terraform in the `./tf/` directory.

#### Scenario: Terraform applies Keycloak resources
- **WHEN** `terraform plan` is run in `./tf/`
- **THEN** resources for keycloak namespace, deployment, service, pvc, and ingress are planned
