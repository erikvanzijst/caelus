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

{{- /*
caelus-sftp.password — the stable per-deployment password. Generated once and
reused from the existing Secret on upgrades (lookup pattern). lookup returns
empty under `helm template`/`--dry-run`; the reconciler always performs real
installs, so the password never spuriously rotates in practice.
*/}}
{{- define "caelus-sftp.password" -}}
{{- $root := .root -}}
{{- $secretName := .secretName | default (printf "%s-sftp-credentials" $root.Release.Name) -}}
{{- $existing := lookup "v1" "Secret" $root.Release.Namespace $secretName -}}
{{- if $existing -}}
{{- index $existing.data "password" | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}

{{- /* Common labels for SFTP resources. */ -}}
{{- define "caelus-sftp.labels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/managed-by: caelus
caelus.dev/component: sftp
{{- end -}}

{{- /*
caelus-sftp.resources — the four standalone objects (Secret, ConfigMap,
Service, Pipe). Rendered from the wrapper's own template file (which has
.Release.*), so it is used by both wrapper-owned and subchart products.

Optional params (defaults suit wrapper-owned products):
  internalUser     upstream sshd username = Pipe `to.username`
                   (default: release name). Subchart products pass a fixed
                   value (e.g. "sftp") because their sidecar lives in static
                   subchart values that cannot reference .Release.Name; the
                   Pipe still routes the unique external release-name to it.
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
The external SFTP username (what the client types) is always the release name.
*/}}
{{- define "caelus-sftp.resources" -}}
{{- $root := .root -}}
{{- $internalUser := .internalUser | default $root.Release.Name -}}
{{- $internalUid := .internalUid | default 1000 -}}
{{- $internalGid := .internalGid | default $internalUid -}}
{{- $credsSecret := .credsSecret | default (printf "%s-sftp-credentials" $root.Release.Name) -}}
{{- $password := include "caelus-sftp.password" (dict "root" $root "secretName" $credsSecret) -}}
{{- $scriptsConfigMap := .scriptsConfigMap | default (printf "%s-sftp-scripts" $root.Release.Name) -}}
{{- $serviceName := .serviceName | default (printf "%s-sftp" $root.Release.Name) -}}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $credsSecret }}
  labels:
    {{- include "caelus-sftp.labels" (dict "root" $root) | nindent 4 }}
type: Opaque
stringData:
  username: {{ $root.Release.Name }}
  password: {{ $password | quote }}
  users.conf: {{ printf "%s:%s:%v:%v" $internalUser $password $internalUid $internalGid | quote }}
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
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $serviceName }}
  labels:
    {{- include "caelus-sftp.labels" (dict "root" $root) | nindent 4 }}
spec:
  selector:
    {{- include "caelus-sftp.podSelector" (dict "root" $root "selector" .selector) | nindent 4 }}
  ports:
    - name: ssh
      protocol: TCP
      port: 2222
      targetPort: 2222
---
apiVersion: sshpiper.com/v1beta1
kind: Pipe
metadata:
  name: {{ $root.Release.Name }}
  labels:
    {{- include "caelus-sftp.labels" (dict "root" $root) | nindent 4 }}
spec:
  from:
    - username: {{ $root.Release.Name | quote }}
  to:
    host: {{ $serviceName }}.{{ $root.Release.Namespace }}.svc:2222
    username: {{ $internalUser | quote }}
    # Released sshpiperd still requires this despite the upstream deprecation
    # note; without it connections fail with "knownhosts: key is unknown".
    ignore_hostkey: true
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
- name: sftp-scripts
  configMap:
    name: {{ $root.Release.Name }}-sftp-scripts
    defaultMode: 0755
{{- end -}}
