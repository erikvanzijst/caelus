## Why

Users have no way to inspect or retrieve the files their deployed applications store on their PVCs (uploads, media, configs, exports). Offering read-only SFTP access — like PikaPods' file access — lets users browse and download their data with any standard SFTP client, strengthening the "your data is yours" story without adding per-app features.

## What Changes

- Deploy a stateless SSH entry point (`sshpiperd` with its Kubernetes plugin) per environment, routing incoming connections to per-deployment SFTP endpoints by SSH username. No restarts on deploy: routes are `Pipe` CRs picked up live. Ports are per-environment Terraform variables. User-facing endpoints: prod at `freepod.eu:22`, dev at `dev.freepod.eu:23` — both environments share the single public IP, and SSH has no SNI, so distinct ports are the only way to address distinct environments. The home router translates these to the internal chain (HAProxy and cluster node listen on 2222 prod / 2223 dev, since both hosts keep their system sshd on port 22).
- Extend product wrapper charts (for products with user-visible PVCs) to declaratively render:
  - an `atmoz/sftp` sidecar container in the app pod with read-only mounts of the exposable PVCs (SFTP/SCP only, no shell),
  - a per-deployment credentials `Secret` (username = release name, password generated once via the Helm `lookup` pattern),
  - a `Service` on the sidecar's SSH port and a `Pipe` CR routing the username to it.
- Database PVCs (e.g., Postgres data dirs) are never mounted into the sidecar; products with zero exposable PVCs render none of the above.
- Widen the tenant baseline NetworkPolicy to allow ingress from the sshpiper deployment to tenant pods (**modifies platform isolation policy**).
- API endpoint to read a deployment's SFTP credentials/connection details; UI panel to display them (host, port, username, password).

Out of scope for this change: rsync/rclone/borg custom commands (future extension), public-key auth, standalone per-namespace SFTP pods (revisit after CephFS/RWX migration), per-user logins spanning multiple deployments, write access.

## Capabilities

### New Capabilities

- `sftp-edge-routing`: cluster-level SSH entry point — sshpiperd deployment (Terraform, `tf/deps/`), Pipe CRD installation, stable host key, NodePort/HAProxy TCP path for port 22, username-based routing with live route updates.
- `sftp-chart-contract`: the wrapper-chart contract for SFTP exposure — sidecar container, read-only mounts, credentials Secret with stable password across upgrades, Service, Pipe CR, zero-PVC and multi-PVC behavior, no-shell guarantee.
- `sftp-credentials-api`: API surface for retrieving a deployment's SFTP connection details (host, port, username, password) with proper authorization; parity CLI command.
- `sftp-credentials-ui`: UI presentation of SFTP access details on the deployment view, including absence handling for products without file access.

### Modified Capabilities

- `deployment-network-isolation`: the baseline tenant policy's ingress allowances gain a rule permitting the platform SFTP router (sshpiper) to reach tenant pods; currently only Traefik and same-namespace ingress are allowed.

## Impact

- `tf/deps/`: installs the cluster-scoped Pipe CRD (shared singleton).
- `tf/app/`: per-environment sshpiper deployment, host-key Secret, RBAC, and NodePort exposure, with the public SSH port as a Terraform variable per workspace; HAProxy edge config (external) gains one TCP passthrough frontend per environment port.
- `products/*/chart/`: charts for products with user-visible data gain sidecar/Secret/Service/Pipe templates (helloworld first, then nextcloud, immich, vaultwarden, matrix, mattermost as applicable).
- `api/`: new read endpoint (deployment-scoped) that fetches the credentials Secret from the cluster; authorization guards; CLI parity.
- `ui/`: new component on the deployment detail view showing SFTP connection info.
- `api/app/services/` reconciler: no new runtime responsibilities (design goal — everything deploy-time declarative via charts).
- New third-party runtime component on the critical path of port 22: `sshpiperd` (validated by an initial spike).
