{{- /*
The `sftp` access profile: read-only SFTP over a deployment's data PVCs, served
by `atmoz/sftp`. One of the library's two profiles; a product chart calls this
set or `ssh-sidecar.dev.*` (_dev.tpl), never both. See README.md.

What this profile promises and the `dev` profile does not: no shell, no writes,
no port forwarding. `atmoz/sftp` hardcodes `AllowTcpForwarding no`, forces
`internal-sftp -R`, and chroots every session.

**This profile's own precondition is that the product has something to expose.**
A deployment with no exposable PVC would get a sidecar offering an empty
session, so `ssh-sidecar.sftp.sidecar` refuses to render without mounts. That is
a property of this profile rather than of the chart contract: the `dev` profile
mounts no tenant volume at all and is correct doing so.

Example call sites in a product chart:

  # standalone resources (own template file, e.g. templates/sftp.yaml):
  {{ include "ssh-sidecar.sftp.resources" (dict "root" .) }}

  # sidecar container, spliced into a wrapper-owned pod's `containers:`:
  {{ include "ssh-sidecar.sftp.sidecar" (dict "root" . "mounts" (list
       (dict "volume" "data" "path" "data"))) }}

  # supporting volumes, spliced into that pod's `volumes:`:
  {{ include "ssh-sidecar.sftp.volumes" (dict "root" .) }}
*/}}

{{- /*
ssh-sidecar.sftp.resources — this profile's standalone objects: the
credentials Secret and the sshd-init ConfigMap, plus the shared Service. Rendered from the wrapper's own template file (which has .Release.*),
so it is used by both wrapper-owned and subchart products.

Required value:
  caelus.ssh.platformPublicKey  the platform's SSH public key, the only key
                   the sidecar trusts. Set per environment; the edge holds the
                   private half. Rendering fails without it.

Optional params (defaults suit wrapper-owned products):
  internalUid      uid the sftp user runs as (default 1000). MUST match the
                   uid that owns the exposed data when the app restricts it to
                   its own user (e.g. nextcloud locks its data dir to 0770
                   www-data=33, so nextcloud passes internalUid=33). Otherwise
                   listing fails with "Permission denied" despite a good login.
  internalGid      gid the sftp user runs as (default = internalUid).
  credsSecret      Secret name (default "<release>-ssh-credentials").
  scriptsConfigMap ConfigMap name (default "<release>-ssh-scripts").
  serviceName      Service name (default "<release>-ssh"), passed through to
                   the shared `ssh-sidecar.service` helper.
  selector         Service pod selector (default: instance label). Subchart
                   products pass the upstream pod's labels.

The SFTP username is always the release name, inside and out. The edge derives
it from the deployment record and reads no cluster object, so it cannot be
overridden per product.
*/}}
{{- define "ssh-sidecar.sftp.resources" -}}
{{- $root := .root -}}
{{- $internalUser := $root.Release.Name -}}
{{- $internalUid := .internalUid | default 1000 -}}
{{- $internalGid := .internalGid | default $internalUid -}}
{{- $credsSecret := .credsSecret | default (printf "%s-ssh-credentials" $root.Release.Name) -}}
{{- $scriptsConfigMap := .scriptsConfigMap | default (printf "%s-ssh-scripts" $root.Release.Name) -}}
{{- $serviceName := .serviceName | default (printf "%s-ssh" $root.Release.Name) -}}
{{- $sshValues := (($root.Values.caelus | default dict).ssh | default dict) -}}
{{- $platformKey := required "caelus.ssh.platformPublicKey is required: without it the sidecar trusts no key and the edge cannot log in" $sshValues.platformPublicKey -}}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $credsSecret }}
  labels:
    {{- include "ssh-sidecar.labels" (dict "root" $root) | nindent 4 }}
type: Opaque
stringData:
  username: {{ $root.Release.Name }}
  # Empty password field: atmoz/sftp runs `usermod -p "*"`, disabling password
  # login. Keys only.
  users.conf: {{ printf "%s::%v:%v" $internalUser $internalUid $internalGid | quote }}
  platform_key.pub: {{ $platformKey | quote }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $scriptsConfigMap }}
  labels:
    {{- include "ssh-sidecar.labels" (dict "root" $root) | nindent 4 }}
data:
  # atmoz/sftp runs /etc/sftp.d/*.sh before starting sshd. Force read-only SFTP
  # (belt-and-suspenders with the read-only volume mounts) and move sshd to the
  # platform sidecar-port convention (2222) that the tenant NetworkPolicy admits
  # sshpiper on.
  init.sh: |
    #!/bin/sh
    sed -i 's/^ForceCommand.*/ForceCommand internal-sftp -R/' /etc/ssh/sshd_config
    echo "Port 2222" >> /etc/ssh/sshd_config
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
    echo "KbdInteractiveAuthentication no" >> /etc/ssh/sshd_config
---
{{ include "ssh-sidecar.service" (dict "root" .root "serviceName" .serviceName "selector" .selector) }}
{{- end -}}

{{- /*
ssh-sidecar.sftp.sidecar — the atmoz/sftp container. Splice into a pod's
`containers:` list. `mounts` is a list of {volume, path[, subPath]}: `volume`
is an existing pod volume (a data PVC), `path` is the subdirectory under the
SFTP home the user sees, and optional `subPath` exposes only a subdirectory of
the volume (use this when the PVC also holds app source or config that must not
be readable — e.g. nextcloud's config.php with DB credentials). The user spec
comes from users.conf (mounted, not args), so it never appears in the pod spec.
NEVER list a database PVC here.

`mounts` is REQUIRED and must be non-empty: this profile exists to expose a
PVC, and a sidecar with nothing mounted offers a session that can list nothing.
*/}}
{{- define "ssh-sidecar.sftp.sidecar" -}}
{{- if not .mounts -}}
{{- fail "ssh-sidecar.sftp.sidecar: `mounts` is empty. The sftp profile exists to expose a data PVC; a product with nothing to expose must render no SSH resources at all rather than a sidecar offering an empty session. If this product has no PVC, it wants the dev profile or no profile." -}}
{{- end -}}
{{- $root := .root -}}
- name: sftp
  image: {{ .image | default "atmoz/sftp:alpine" }}
  ports:
    - containerPort: 2222
  # atmoz/sftp regenerates SSH host keys on every start (nothing persists
  # /etc/ssh), so the startup probe holds liveness off until sshd first binds;
  # 30 x 5s comfortably exceeds RSA-4096 generation. Neither probe touches the
  # app container, the exposed PVCs, or any credential.
  startupProbe:
    tcpSocket:
      port: 2222
    periodSeconds: 5
    failureThreshold: 30
  livenessProbe:
    tcpSocket:
      port: 2222
    periodSeconds: 10
    timeoutSeconds: 3
    failureThreshold: 3
  volumeMounts:
    {{- range .mounts }}
    - name: {{ .volume }}
      mountPath: /home/{{ $root.Release.Name }}/{{ .path }}
      {{- if .subPath }}
      subPath: {{ .subPath }}
      {{- end }}
      readOnly: true
    {{- end }}
    - name: sftp-users
      mountPath: /etc/sftp
      readOnly: true
    # atmoz/sftp concatenates every file here into the user's authorized_keys
    # at startup, with the ownership and mode sshd requires.
    - name: sftp-platform-key
      mountPath: /home/{{ $root.Release.Name }}/.ssh/keys
      readOnly: true
    - name: sftp-scripts
      mountPath: /etc/sftp.d
      readOnly: true
  resources:
    requests:
      cpu: 10m
      memory: 16Mi
    limits:
      memory: 64Mi
{{- end -}}

{{- /*
ssh-sidecar.sftp.volumes — the sidecar's own supporting volumes (credentials +
init script). Splice into the pod's `volumes:` list. The data PVC volumes are
already declared by the product; this adds only the SFTP-specific ones.

`credsSecret` and `scriptsConfigMap` default exactly as they do in
`ssh-sidecar.sftp.resources`, and a product overriding either there MUST pass the
same value here: these volumes name the objects that helper renders, and a
mismatch is a pod referencing a Secret nobody emitted.
*/}}
{{- define "ssh-sidecar.sftp.volumes" -}}
{{- $root := .root -}}
{{- $credsSecret := .credsSecret | default (printf "%s-ssh-credentials" $root.Release.Name) -}}
{{- $scriptsConfigMap := .scriptsConfigMap | default (printf "%s-ssh-scripts" $root.Release.Name) -}}
- name: sftp-users
  secret:
    secretName: {{ $credsSecret }}
    items:
      - key: users.conf
        path: users.conf
- name: sftp-platform-key
  secret:
    secretName: {{ $credsSecret }}
    items:
      - key: platform_key.pub
        path: platform_key.pub
- name: sftp-scripts
  configMap:
    name: {{ $scriptsConfigMap }}
    defaultMode: 0755
{{- end -}}
