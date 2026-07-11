## 1. Spike: validate sshpiperd (go/no-go gate)

- [x] 1.1 Deploy sshpiperd (kubernetes plugin, `SSHPIPERD_KUBERNETES_ALL_NAMESPACES=true`) with its Pipe CRD, RBAC, and a host-key Secret on the dev cluster; expose via NodePort
- [x] 1.2 Hand-write one Pipe and an `atmoz/sftp` sidecar on a manual helloworld install; verify password passthrough, SFTP subsystem, read-only enforcement, and shell denial through the full path
- [x] 1.3 Verify Pipe hot-reload: add/remove a second Pipe while a session is open on the first; confirm the open session is undisturbed
- [x] 1.4 Measure sidecar idle memory and pick resource requests/limits; resolve the design's open questions (password passthrough config, `users.conf` plaintext vs `:e` hash, whether the kubernetes plugin can scope its Pipe watch by namespace/label for per-environment filtering, low-port node binding via k3s ServiceLB vs widened NodePort range); record findings in design.md

## 2. Edge routing infrastructure (tf/deps + tf/app)

- [x] 2.1 Install the cluster-scoped Pipe CRD via `tf/deps/`
- [x] 2.2 Add a per-environment sshpiperd module to `tf/app/`: Deployment, host-key Secret, ServiceAccount + cluster RBAC for Pipes, node exposure on the cluster-side SSH port as a workspace variable (defaults: prod 2222, dev 2223; binding mechanism per spike finding)
- [ ] 2.3 Apply to the dev workspace and add the dev HAProxy TCP frontend :2223 → cluster node :2223; configure router forward :23 → HAProxy :2223; document the edge config location
- [ ] 2.4 End-to-end smoke test on dev: `sftp -P 23 <user>@dev.freepod.eu` from outside the LAN using the spike Pipe; verify `ssh -p 22` to the homelab host and cluster node still reaches their system OpenSSH
- [ ] 2.5 Apply to the prod workspace, add the prod HAProxy TCP frontend :2222 → cluster node :2222, and configure router forward :22 → HAProxy :2222 once dev is validated

## 3. Network isolation carve-out

- [x] 3.1 Extend the baseline NetworkPolicy template with an ingress rule from the sshpiper namespace/pod label to port 2222/TCP; add the sshpiper selector and port to the configurable isolation settings with cluster-matching defaults
- [x] 3.2 Update isolation tests for the new rule (allowed on 2222, denied on other ports, cross-environment proxy denied)
- [x] 3.3 Run the fleet-wide policy sync against dev and verify existing deployments converge without disruption

## 4. Chart contract (helloworld first)

- [x] 4.1 Add SFTP templates to the helloworld wrapper chart: `atmoz/sftp` sidecar with read-only PVC mounts, `internal-sftp -R` + no-shell sshd config, credentials Secret (username = release name, `lookup`-stable password), Service :2222, Pipe CR; all conditional on the chart exposing PVCs
- [x] 4.2 Verify via reconciler-driven install: credentials from the Secret authenticate, data PVC visible read-only, writes and shell rejected, password stable across a `helm upgrade`
- [x] 4.3 Extract the reusable template blocks (named templates or documented copy pattern) and document the chart contract for product authors, including the DB-PVC exclusion rule and zero-PVC behavior
- [x] 4.4a nextcloud: SFTP over data subPath via upstream extraSidecarContainers; fixed internal user + uid 33; live-tested end-to-end
- [x] 4.4b mattermost: SFTP over data PVC (wrapper Deployment); uid 2000; render-verified (uid set to image user; not live-installed)
- [x] 4.4c matrix + vaultwarden: confirmed zero-SFTP rendering (only PVCs are DB/secret stores; no dependency added)
- [x] 4.4d immich: SFTP over library PVC via bjw-s `advancedMounts` (single volume, two mounts — a second volume for the RWO claim deadlocks on local-path); `maxSurge: 0` so the old server pod releases the library before the new one starts. Upgrade-safety verified live: PVC UIDs unchanged, data markers survived, no PVC/DB recreation.

## 5. Credentials API

- [x] 5.1 Service function reading the credentials Secret from a deployment's namespace via the Kubernetes API, with not-found semantics for deployments without SFTP
- [x] 5.2 Add SFTP host/port to application settings (pydantic-settings; user-facing router values: `freepod.eu:22` prod, `dev.freepod.eu:23` dev); `GET /users/{user_id}/deployments/{deployment_id}/sftp` endpoint returning host/port/username/password, guarded by existing deployment authorization
- [x] 5.3 CLI parity command
- [x] 5.4 API + CLI tests (owner, admin, non-owner denied, absent-secret 404)

## 6. Credentials UI

- [x] 6.1 `SftpAccessPanel` component under `ui/src/components/`: host/port/username, masked password with reveal, copy buttons, read-only note
- [x] 6.2 Wire into the deployment detail view; hide the panel entirely on the API's not-available response

## 7. Verification & docs

- [ ] 7.1 Full e2e on dev: deploy nextcloud via the UI, read credentials from the UI, connect with an SFTP client from outside, browse and download; confirm DB PVC invisible
- [x] 7.2 Concurrent-session check: deploy a new app while an SFTP session is open; session survives (verified in task 1.3 — Pipe add/delete with an open session undisturbed, zero proxy restarts)
- [x] 7.3 Update k8s/architecture.md (or a new doc) with the SFTP architecture and the future extension notes (pubkey auth, rsync/rclone/borg, standalone SFTP pods post-CephFS) — see k8s/docs/sftp-file-access.md
