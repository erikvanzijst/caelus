## Context

Freepod runs a single-node **k3s** cluster (`192.168.0.159`). It sits behind the **homelab**
cluster's HAProxy SNI edge (`github.com/erikvanzijst/homelab`, `helm/haproxy/`): public
`freepod.eu` → HAProxy `:443` (TLS passthrough, `send-proxy-v2`) → freepod node `:443`, where
**freepod Traefik terminates TLS**. Freepod Traefik must therefore trust PROXY protocol from the
edge (`proxyProtocol.trustedIPs`, `haproxy_edge_ip` default `192.168.0.12/32`), serve the
`*.freepod.eu` wildcard as its default cert, and own the node's host `:80/:443` via klipper.

Today that Traefik is the **k3s-bundled** one, configured by amending the bundled chart with a
`HelmChartConfig/traefik` (`tf/deps/system/traefik.tf`, `kubernetes_manifest.traefik_config`,
`terraform import`ed from the pre-existing object). This collides with a stale hand-created host
manifest `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml` that defines the *same* object
with the *old* `forwardedheaders.insecure` config. k3s's `deploy` addon controller re-applies that
file on every k3s (re)start, reverting the Terraform config — which is exactly what broke
`freepod.eu` on 2026-07-01 when unattended-upgrades + needrestart bounced `k3s.service`.

The **homelab** cluster already solved this class of problem: it sets `--disable=traefik` on the
node and manages Traefik as a Helm release (`helm/traefik/`), and explicitly **rejected**
re-enabling the bundled Traefik via HelmChartConfig ("requires node changes and risks a klipper
enable-race"). This change brings freepod onto the same model.

## Goals / Non-Goals

**Goals:**
- Make Terraform the **single source of truth** for freepod Traefik, immune to the k3s `deploy`
  addon controller replaying a host manifest on restart.
- Preserve **all** current TLS-termination behaviour byte-for-byte (wildcard default cert, PROXY
  protocol trust from the edge, `externalTrafficPolicy: Local`, websecure-default entrypoint, no
  entrypoint-level redirect, nginx-ingress provider, external-name services).
- Keep the node's `:80/:443` owned by Traefik via klipper (`LoadBalancer`), since the HAProxy edge
  connects to the node's host ports from another cluster.
- Mirror homelab's `helm/traefik/` module structure for consistency.

**Non-Goals:**
- Zero-downtime cutover. This runs in a maintenance window; a brief ingress blip while klipper
  hands `:80/:443` from the bundled Traefik to the new release is acceptable (no ClusterIP
  coexistence dance).
- Changing HAProxy, the homelab edge, DNS, or the `haproxy_edge_ip`.
- Changing any app Ingress, the reconciler (`api/`), product charts, `redirect_https.tf`, or the
  cert-manager issuers/solver pinning.
- Bumping Traefik across a major (stay on **v3.6.x** for parity; a later change may track newer).

## Decisions

### D1: Self-managed `helm_release`, bundled Traefik disabled (not "amend the bundled chart")

**Decision:** Add `tf/deps/system/helm/traefik/` (a `helm_release` from the upstream Traefik chart
repo + `values.yaml`), disable the k3s-bundled Traefik on the node (`disable: [traefik]`), remove
the stale host `traefik-config.yaml`, and delete `tf/deps/system/traefik.tf`.

**Rationale:** The bundled-chart + `HelmChartConfig` pattern is inherently a two-owner setup: the
k3s `deploy` controller re-applies `/var/lib/rancher/k3s/server/manifests/*` on every restart and
will clobber any externally-managed object of the same name. A self-managed Helm release with the
bundled addon disabled removes the second owner entirely, so no restart can revert the config. This
is the pattern homelab already runs and validated.

**Alternatives rejected:**
- *Just delete the stale host file, keep amending the bundled chart.* Fixes this recurrence but
  keeps freepod on the fragile "amend the k3s addon" pattern and leaves k3s owning the chart
  version (why the running image drifted to `3.6.7` vs the intended `3.6.10`). Rejected as the
  durable answer (it was the "minimal" option the operator declined).
- *Rewrite the stale host file with the correct config.* Still two owners; still breaks if k3s ever
  ships a different default. Rejected.

### D2: `LoadBalancer` + `externalTrafficPolicy: Local` (the freepod-specific divergence from homelab)

**Decision:** The freepod Traefik Service is `type: LoadBalancer` with `externalTrafficPolicy: Local`
and host ports 80/443, so klipper/servicelb binds the node's `:80/:443`.

**Rationale:** Unlike homelab (where HAProxy and Traefik are in the *same* cluster, so Traefik is
`ClusterIP` reached in-cluster), freepod's Traefik is reached by the homelab HAProxy across clusters
at the node's **host** `:443`. It must therefore own the host ports. `Local` is mandatory: with the
default `Cluster` policy, kube-proxy SNATs the source to the CNI gateway (`10.42.0.1`) before
Traefik sees it, so `proxyProtocol.trustedIPs=<edge>` never matches and the PROXY header (and real
client IP) is lost.

### D3: Port the full value surface verbatim; no behavioural change

**Decision:** `values.yaml` reproduces exactly what the retired `HelmChartConfig` produced:
`ports.websecure.asDefault: true` / `ports.web.asDefault: false`; `proxyProtocol.trustedIPs` on both
entrypoints (= `var.haproxy_edge_ip`) with `forwardedheaders.insecure` **absent**;
`tlsStore.default.defaultCertificate.secretName: wildcard-freepod-eu-tls`;
`providers.kubernetesIngress.allowExternalNameServices: true`;
`providers.kubernetesIngressNginx.enabled: true`; `accesslog: true`; `ingressClass` name `traefik`
kept as default; and **no** `ports.web.http.redirections` (the entrypoint-level redirect that
deadlocks HTTP-01 — the low-priority web-only redirect IngressRoute in `redirect_https.tf` stays the
sole redirect).

**Rationale:** The `freepod-tls-termination` spec's behavioural requirements are unchanged; only the
*delivery vehicle* moves from a `HelmChartConfig` to `helm_release` values. Reproducing the surface
exactly keeps every existing scenario (wildcard cert, client-IP, ACME redirect, entrypoint default)
green. `var.haproxy_edge_ip` is already threaded into `tf/deps/system`; reuse it.

### D4: CRDs survive the cutover; watch first-apply CRD-at-plan-time

**Decision:** Rely on the `traefik.io/v1alpha1` CRDs persisting across the bundled-chart uninstall
(Helm does not delete CRDs on `uninstall`), so `redirect_https.tf`'s Middleware/IngressRoute keep
resolving. If any `kubernetes_manifest` in the new module references a Traefik CRD, apply the module
in two passes on first rollout (`-target` the `helm_release`, then full apply), as homelab's module
notes — but freepod's module is a plain `helm_release` + `values.yaml`, so this is only a caveat.

**Rationale:** The cutover must not orphan the redirect IngressRoute or the solver wiring. Since the
CRDs are not garbage-collected by the uninstall and the new chart re-declares them, dependent CRs
stay valid.

### D5: Cutover ordering (maintenance window, disable-then-apply)

**Decision:**
1. Land the tf changes (add module, remove `traefik.tf`) and review `terraform plan`.
2. On the node: write `/etc/rancher/k3s/config.yaml` (`disable: [traefik]`), remove the stale
   `traefik-config.yaml`, `systemctl restart k3s`. k3s uninstalls the bundled Traefik and its
   `svclb`, freeing host `:80/:443`. **Ingress is down here.**
3. `terraform apply` the new module; the `LoadBalancer` Traefik comes up and klipper binds
   `:80/:443`. **Ingress restored.**
4. Verify (see tasks §5), including a **deliberate `systemctl restart k3s`** to confirm the config
   no longer reverts.

**Rationale:** Two `LoadBalancer` services cannot both own klipper's `:80/:443`, so the bundled one
must release the ports before the new one can bind them — a short gap. The operator accepted a
maintenance-window blip over a more complex coexistence sequence.

### D6: Chart version pinned to Traefik v3.6.x

**Decision:** Pin the Helm chart `version` to the release that ships **Traefik app v3.6.x** (parity
with the current `3.6.10`), exposed as a module variable (default set to the resolved chart
version), matching homelab's `traefik_chart_version` pattern.

**Rationale:** Avoid coupling the cutover with a Traefik minor/major bump. Owning the chart version
in tf (vs k3s choosing it) is itself a benefit — it removes the silent `3.6.7`-vs-`3.6.10` drift the
bundled chart introduced.
