## ADDED Requirements

### Requirement: Grafana with pre-wired datasources

The system SHALL run Grafana in the `monitoring` namespace with the Prometheus
and Loki datasources provisioned automatically, so metrics and logs are
queryable without manual datasource setup.

#### Scenario: Datasources are available on first login

- **WHEN** an authorized user opens Grafana after deployment
- **THEN** the Prometheus datasource (metrics) and Loki datasource (logs) are
  already present and usable

### Requirement: Terraform-managed dashboards

The system SHALL provision dashboards through the Grafana Helm chart so they
exist automatically on deploy, including Node Exporter Full (gnetId `1860`) and
Kubernetes Traefik Ingress NextGen (gnetId `25330`).

#### Scenario: Dashboards exist after a fresh deploy

- **WHEN** the monitoring stack is applied to a cluster with no prior Grafana
  state
- **THEN** the Node Exporter Full and Traefik Ingress NextGen dashboards are
  present without any manual import

#### Scenario: Traefik dashboard renders data

- **WHEN** an operator opens the Traefik Ingress NextGen dashboard
- **THEN** it displays live ingress data, because Traefik's Prometheus metrics
  are enabled and scraped

### Requirement: Keycloak-authenticated access with a user whitelist

The system SHALL expose Grafana at `grafana.freepod.eu` and authenticate users
via native Keycloak OIDC, restricting access to members of a designated
Keycloak group (the whitelist). Users outside the group SHALL be denied.

#### Scenario: Whitelisted user signs in

- **WHEN** a user who is a member of the `freepod-observability` Keycloak group
  authenticates through Grafana's OIDC login
- **THEN** they are granted access with a mapped Grafana role

#### Scenario: Non-whitelisted user is denied

- **WHEN** a user who is not a member of the group attempts to sign in
- **THEN** Grafana refuses the login (strict role/group enforcement), granting
  no default access

#### Scenario: Whitelist is managed in Keycloak

- **WHEN** an operator needs to grant or revoke a user's Grafana access
- **THEN** it is done by adding/removing that user from the Keycloak group, with
  no Terraform apply or Grafana user-list change required

### Requirement: Grafana ingress without edge forward-auth

The system SHALL route `grafana.freepod.eu` through Traefik with HTTPS/HSTS
consistent with other freepod ingresses, and SHALL NOT place a forward-auth
middleware in front of Grafana, since Grafana performs its own OIDC login.

#### Scenario: Grafana handles its own login

- **WHEN** an unauthenticated request reaches `grafana.freepod.eu`
- **THEN** Traefik forwards it to Grafana (no edge forward-auth), and Grafana
  initiates the Keycloak OIDC sign-in flow itself
