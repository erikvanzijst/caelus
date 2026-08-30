{{- /*
caelus-sftp library chart.

Provides read-only SFTP access to a deployment's data PVCs, routed through the
platform's shared sshpiper by SSH username (= release name). See README.md.

All helpers take a dict; `root` is always the top-level chart context (needed
for .Release.* and cluster lookups). Example call sites in a product chart:

  # standalone resources (own template file, e.g. templates/sftp.yaml):
  {{ include "caelus-sftp.resources" (dict "root" .) }}

  # sidecar container, spliced into a wrapper-owned pod's `containers:`:
  {{ include "caelus-sftp.sidecar" (dict "root" . "mounts" (list
       (dict "volume" "data" "path" "data"))) }}

  # supporting volumes, spliced into that pod's `volumes:`:
  {{ include "caelus-sftp.volumes" (dict "root" .) }}
*/}}

{{- /* Common labels for SFTP resources. */ -}}
{{- define "caelus-sftp.labels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/managed-by: caelus
caelus.dev/component: sftp
{{- end -}}

{{- /*
caelus-sftp.resources — the three standalone objects (Secret, ConfigMap,
Service). Rendered from the wrapper's own template file (which has .Release.*),
so it is used by both wrapper-owned and subchart products.

Required value:
  caelus.sftp.platformPublicKey  the platform's SSH public key, the only key
                   the sidecar trusts. Set per environment; the edge holds the
                   private half. Rendering fails without it.

Optional params (defaults suit wrapper-owned products):
  internalUid      uid the sftp user runs as (default 1000). MUST match the
                   uid that owns the exposed data when the app restricts it to
                   its own user (e.g. nextcloud locks its data dir to 0770
                   www-data=33, so nextcloud passes internalUid=33). Otherwise
                   listing fails with "Permission denied" despite a good login.
  internalGid      gid the sftp user runs as (default = internalUid).
  credsSecret      Secret name (default "<release>-sftp-credentials").
  scriptsConfigMap ConfigMap name (default "<release>-sftp-scripts").
  serviceName      Service name (default "<release>-sftp").
  selector         Service pod selector (default: instance label). Subchart
                   products pass the upstream pod's labels.

The SFTP username is always the release name, inside and out. The edge derives
it from the deployment record and reads no cluster object, so it cannot be
overridden per product.
*/}}
{{- define "caelus-sftp.resources" -}}
{{- $root := .root -}}
{{- $internalUser := $root.Release.Name -}}
{{- $internalUid := .internalUid | default 1000 -}}
{{- $internalGid := .internalGid | default $internalUid -}}
{{- $credsSecret := .credsSecret | default (printf "%s-sftp-credentials" $root.Release.Name) -}}
{{- $scriptsConfigMap := .scriptsConfigMap | default (printf "%s-sftp-scripts" $root.Release.Name) -}}
{{- $serviceName := .serviceName | default (printf "%s-sftp" $root.Release.Name) -}}
{{- $sftpValues := (($root.Values.caelus | default dict).sftp | default dict) -}}
{{- $platformKey := required "caelus.sftp.platformPublicKey is required: without it the sidecar trusts no key and the edge cannot log in" $sftpValues.platformPublicKey -}}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $credsSecret }}
  labels:
    {{- include "caelus-sftp.labels" (dict "root" $root) | nindent 4 }}
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
    {{- include "caelus-sftp.labels" (dict "root" $root) | nindent 4 }}
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
apiVersion: v1
kind: Service
metadata:
  name: {{ $serviceName }}
  labels:
    {{- include "caelus-sftp.labels" (dict "root" $root) | nindent 4 }}
spec:
  # The sidecar fronts administration, not the application. Its usefulness peaks
  # when the app container is broken, so application readiness must not gate
  # routing here. Do not drop this: its loss is silent until an app crash-loops.
  publishNotReadyAddresses: true
  selector:
    {{- include "caelus-sftp.podSelector" (dict "root" $root "selector" .selector) | nindent 4 }}
  ports:
    - name: ssh
      protocol: TCP
      port: 2222
      targetPort: 2222
{{- end -}}

{{- /*
caelus-sftp.podSelector — labels the Service uses to find the SFTP sidecar's
pod. Products whose sidecar rides in the upstream subchart's pod MUST override
this by passing `selector` (a dict of label:value) so the Service targets that
pod; otherwise it defaults to the standard Caelus instance label.
*/}}
{{- define "caelus-sftp.podSelector" -}}
{{- if .selector -}}
{{- range $k, $v := .selector }}
{{ $k }}: {{ $v | quote }}
{{- end -}}
{{- else -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}
{{- end -}}

{{- /*
caelus-sftp.sidecar — the atmoz/sftp container. Splice into a pod's
`containers:` list. `mounts` is a list of {volume, path[, subPath]}: `volume`
is an existing pod volume (a data PVC), `path` is the subdirectory under the
SFTP home the user sees, and optional `subPath` exposes only a subdirectory of
the volume (use this when the PVC also holds app source or config that must not
be readable — e.g. nextcloud's config.php with DB credentials). The user spec
comes from users.conf (mounted, not args), so it never appears in the pod spec.
NEVER list a database PVC here.
*/}}
{{- define "caelus-sftp.sidecar" -}}
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
caelus-sftp.volumes — the sidecar's own supporting volumes (credentials +
init script). Splice into the pod's `volumes:` list. The data PVC volumes are
already declared by the product; this adds only the SFTP-specific ones.
*/}}
{{- define "caelus-sftp.volumes" -}}
{{- $root := .root -}}
- name: sftp-users
  secret:
    secretName: {{ $root.Release.Name }}-sftp-credentials
    items:
      - key: users.conf
        path: users.conf
- name: sftp-platform-key
  secret:
    secretName: {{ $root.Release.Name }}-sftp-credentials
    items:
      - key: platform_key.pub
        path: platform_key.pub
- name: sftp-scripts
  configMap:
    name: {{ $root.Release.Name }}-sftp-scripts
    defaultMode: 0755
{{- end -}}
