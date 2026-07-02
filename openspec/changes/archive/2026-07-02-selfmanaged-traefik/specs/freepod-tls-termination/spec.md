## ADDED Requirements

### Requirement: Freepod Traefik is a Terraform-managed Helm release, not the k3s-bundled addon
Freepod Traefik SHALL be deployed as a **Terraform-managed Helm release** (`tf/deps/system/helm/traefik/`,
an upstream-chart `helm_release`), and the **k3s-bundled Traefik SHALL be disabled** on the node via
`/etc/rancher/k3s/config.yaml` (`disable: [traefik]`). No file under
`/var/lib/rancher/k3s/server/manifests/` SHALL define Traefik or a `HelmChartConfig/traefik`. Terraform
is therefore the single source of truth for freepod Traefik's chart version and configuration; the prior
pattern of amending the bundled chart via a `HelmChartConfig` (`kubernetes_manifest.traefik_config`) is
removed.

The Helm release's `values.yaml` SHALL reproduce the existing TLS-termination configuration with no
behavioral change: the `*.freepod.eu` wildcard as the default certificate store, PROXY-protocol trust
from the HAProxy edge IP on `web` and `websecure` (no blanket `forwardedheaders.insecure`), a
`LoadBalancer` Service with `externalTrafficPolicy: Local` owning the node's `:80/:443`, `websecure`
as the default entrypoint, the `kubernetesIngressNginx` provider and `allowExternalNameServices`, the
`traefik` IngressClass as default, and no entrypoint-level HTTP→HTTPS redirect.

#### Scenario: Terraform owns Traefik and the bundled addon is disabled
- **WHEN** the freepod node's k3s configuration is inspected after this change
- **THEN** `/etc/rancher/k3s/config.yaml` disables the bundled Traefik, so k3s renders no Traefik
  addon manifest under `/var/lib/rancher/k3s/server/manifests/` (disabling via the `config.yaml`
  `disable` list writes no `traefik.yaml`/`.skip`; k3s simply never deploys the bundled Traefik)
- **AND** Traefik runs from the Terraform `helm_release`, and no `HelmChartConfig/traefik` or
  host `traefik-config.yaml` manifest exists

#### Scenario: Behavior is preserved after the migration
- **WHEN** an external client connects to `https://<app>.freepod.eu` through the HAProxy edge after cutover
- **THEN** the self-managed Traefik terminates TLS with the `*.freepod.eu` wildcard default certificate,
  strips the edge's PROXY-protocol header (trusted via `proxyProtocol.trustedIPs`), and routes to the app
- **AND** the observable behavior is identical to the pre-migration bundled-chart configuration

### Requirement: Freepod Traefik configuration survives a k3s restart
A restart of `k3s.service` SHALL preserve freepod Traefik's configuration intact — because Terraform
is the sole owner and no host manifest defines Traefik. Whether triggered by Ubuntu
unattended-upgrades + needrestart, a reboot, or a manual restart, the configuration MUST NOT be
reverted by the k3s `deploy` addon controller, which has nothing to replay for Traefik on startup.

#### Scenario: Restart does not revert the config
- **WHEN** `k3s.service` is restarted on the freepod node
- **THEN** the self-managed Traefik and its configuration (PROXY-protocol trust, wildcard default cert,
  `externalTrafficPolicy: Local`, websecure default) remain in place
- **AND** `https://freepod.eu` continues to serve valid TLS with no `record overflow` / plaintext-on-443
  regression, and no bundled Traefik or `HelmChartConfig/traefik` is recreated
