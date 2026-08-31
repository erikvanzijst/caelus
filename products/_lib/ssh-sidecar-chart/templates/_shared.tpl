{{- /*
ssh-sidecar library chart — what both access profiles share.

A product chart is authored for exactly one profile and calls that profile's
helper set: `ssh-sidecar.sftp.*` (_sftp.tpl) or `ssh-sidecar.dev.*` (_dev.tpl).
There is no `profile` parameter and no profile string anywhere — see README.md
and design.md § *The profile is which helpers a chart calls*. Calling one
profile's `resources` beside the other's `sidecar` renders an incoherent chart;
the render assertions in api/tests/ are what catch that.

Everything in this file is profile-independent. The Service especially: it is
the one object the SSH edge depends on, the edge knows nothing about profiles,
and a per-profile copy would only ask two authors to keep agreeing.

All helpers take a dict; `root` is always the top-level chart context (needed
for .Release.* and cluster lookups).
*/}}

{{- /* Common labels for every SSH resource, whichever profile emitted it. */ -}}
{{- define "ssh-sidecar.labels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/managed-by: caelus
caelus.dev/component: ssh
{{- end -}}

{{- /*
ssh-sidecar.service — the Service fronting the sidecar. Emitted by BOTH
profiles through this one helper, never copied into either.

The name follows the platform's single naming convention, `<release>-ssh`,
which the SSH edge uses to derive a deployment's upstream address. **That
convention is shared with `ssh-auth/` and cannot be changed on one side alone**
— a chart rendering a name the edge does not expect produces a deployment that
authenticates and then reaches nothing, and the failure surfaces at the edge
rather than here. See ssh-auth/README.md § Coupling.

Params:
  serviceName  Service name (default "<release>-ssh"). Overriding it makes the
               deployment unroutable; there is no reason to.
  selector     Service pod selector (default: instance label). Products whose
               sidecar rides in an upstream subchart's pod MUST pass the
               labels of that pod.
*/}}
{{- define "ssh-sidecar.service" -}}
{{- $root := .root -}}
{{- $serviceName := .serviceName | default (printf "%s-ssh" $root.Release.Name) -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ $serviceName }}
  labels:
    {{- include "ssh-sidecar.labels" (dict "root" $root) | nindent 4 }}
spec:
  # The sidecar fronts administration, not the application. Its usefulness peaks
  # when the app container is broken, so application readiness must not gate
  # routing here. Do not drop this: its loss is silent until an app crash-loops.
  publishNotReadyAddresses: true
  selector:
    {{- include "ssh-sidecar.podSelector" (dict "root" $root "selector" .selector) | nindent 4 }}
  ports:
    - name: ssh
      protocol: TCP
      port: 2222
      targetPort: 2222
{{- end -}}

{{- /*
ssh-sidecar.podSelector — labels the Service uses to find the sidecar's pod.
Products whose sidecar rides in the upstream subchart's pod MUST override this
by passing `selector` (a dict of label:value) so the Service targets that pod;
otherwise it defaults to the standard Caelus instance label.
*/}}
{{- define "ssh-sidecar.podSelector" -}}
{{- if .selector -}}
{{- range $k, $v := .selector }}
{{ $k }}: {{ $v | quote }}
{{- end -}}
{{- else -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}
{{- end -}}
