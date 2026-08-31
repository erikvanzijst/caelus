{{- /*
The `dev` access profile: the platform's own SSH sidecar, which opens a shell in
the application container and — where the product has a database — carries the
PostgreSQL toolbox and forwards to the pooler. One of the library's two
profiles; a product chart calls this
set or `ssh-sidecar.sftp.*` (_sftp.tpl), never both. See README.md and
products/_lib/ssh-sidecar-image/README.md for the image's own contract.

**This profile defines no Secret and no ConfigMap.** Everything per-deployment
reaches the sidecar as an environment variable: the trusted key is a *public*
key, the allowlist is a host:port, and the database variables come from the
Secret the reconciler already writes. The image writes its own
`authorized_keys`, `sshd_config` and host key at startup, so an object of either
kind would be one nothing reads. `sftp` renders both because `atmoz/sftp` reads
its user list and its startup script off disk; that is a property of that
profile, not of the chart contract.

Two call sites, not three: there are no supporting volumes to splice.

  # the sidecar container, spliced into the pod's `containers:`:
  {{ include "ssh-sidecar.dev.sidecar" (dict "root" . "image" .Values.sshSidecarImage) }}

  # the Service, from its own template file:
  {{ include "ssh-sidecar.dev.resources" (dict "root" .) }}

The pod itself must also set `shareProcessNamespace: true` — a pod-level field a
container helper cannot reach. Without it the container still starts and serves;
forwarding and the toolbox work, and a session that needs the app container says
what is missing. `baseline` Pod Security permits it; it is only the tracing
capability that it refuses.
*/}}

{{- /*
ssh-sidecar.dev.resources — this profile's standalone objects, which are the
shared Service and nothing else.

Params: `serviceName` and `selector`, passed through to `ssh-sidecar.service`.
*/}}
{{- define "ssh-sidecar.dev.resources" -}}
{{ include "ssh-sidecar.service" (dict "root" .root "serviceName" .serviceName "selector" .selector) }}
{{- end -}}

{{- /*
ssh-sidecar.dev.sidecar — the platform SSH sidecar container. Splice into the
pod's `containers:` list.

Required param:
  image  the sidecar image, pinned to an exact version. A **system** value: a
         tenant-settable reference here would let a tenant substitute the
         container that holds the platform's trusted key and enters their
         application container. Never a moving tag — with one, the version a
         pod runs becomes a function of when it last restarted and what its
         node had cached.

Every runtime input below is platform-projected. None is `required` here on
purpose: the image validates all of them and exits naming the offending
variable, which is a pod that will not start rather than one that starts
misconfigured. Failing the render instead would move the diagnosis away from the
container that knows what is wrong.
*/}}
{{- define "ssh-sidecar.dev.sidecar" -}}
{{- $root := .root -}}
{{- $caelus := $root.Values.caelus | default dict -}}
{{- $db := $caelus.database | default dict -}}
{{- $ssh := $caelus.ssh | default dict -}}
- name: ssh
  image: {{ required "ssh-sidecar.dev.sidecar: `image` is required, pinned to an exact version. It is a system value; see products/_lib/ssh-sidecar-image/README.md." .image | quote }}
  # The tag is immutable, so tag and content are one to one and caching is
  # correct rather than accidental.
  imagePullPolicy: IfNotPresent
  ports:
    - containerPort: 2222
  env:
    # The only key this server trusts. The tenant's own keys are checked by the
    # edge on the downstream leg, never here.
    - name: FREEPOD_AUTHORIZED_KEYS
      value: {{ $ssh.platformPublicKey | default "" | quote }}
    {{- if and $db.host $db.port }}
    # The forward allowlist. `PermitOpen` matches the destination **as the
    # client wrote it** and resolves it afterwards, so this spelling and the one
    # the platform documents must agree byte for byte -- a mismatch produces a
    # refusal that reads like an authorization failure rather than a typo.
    #
    # Rendered only for a product that has a database, because that endpoint is
    # the only thing this profile forwards to.
    - name: FREEPOD_PERMIT_OPEN
      value: {{ printf "%s:%v" $db.host $db.port | quote }}
    {{- end }}
    # From the pod label rather than from `caelus.releaseId`, which is the same
    # fact and one fewer indirection. The label is what the log pipeline
    # relabels into the release stream, so a session and the logs of the pod it
    # landed on cannot disagree. Two independent projections can; one cannot.
    - name: FREEPOD_RELEASE_ID
      valueFrom:
        fieldRef:
          fieldPath: metadata.labels['caelus.dev/release-id']
    # The account the SSH edge authenticates the upstream leg as. The edge has
    # ONE username convention -- the deployment name -- because on the `sftp`
    # profile that is the account atmoz creates, and the edge is deliberately
    # ignorant of which profile it is addressing (ssh-auth/README.md). This
    # server needs uid 0, so the image adds the deployment name as a second
    # uid-0 account rather than the edge learning a second convention. Without
    # it every connection is refused with `Invalid user`, which reads at the
    # client as an authorization failure.
    - name: FREEPOD_LOGIN_USER
      value: {{ $root.Release.Name | quote }}
  {{- with $db.secretName }}
  # The database variables reach the sidecar's OWN environment, not the
  # application's. A developer connects precisely when the application is
  # broken, and details read from a crash-looping process are unavailable then.
  envFrom:
    - secretRef:
        name: {{ . | quote }}
  {{- end }}
  securityContext:
    # **No `CAP_SYS_PTRACE`, deliberately, and this is a deferred gap rather
    # than a decision.** Tenant namespaces enforce Pod Security `baseline`
    # (api/app/network_policy.py), which forbids every non-default capability;
    # a pod requesting it is refused at admission with `violates PodSecurity
    # "baseline:latest"` and never schedules. Granting it needs the namespace
    # raised to `privileged` for products on this profile, which is a
    # reconciler change and a real relaxation, so it is tracked separately.
    #
    # What this costs is `strace`, `gdb` and `py-spy` only. Entering the
    # application container does NOT need it: the dispatcher chroots into
    # /proc/<pid>/root, which needs `CAP_SYS_CHROOT` from the default set
    # (var/ssh_access.md D4). The shell, file copy, the toolbox and forwarding
    # all work without it.
    privileged: false
    allowPrivilegeEscalation: true
    # Root, which is what reading and entering another container's process
    # filesystem requires. The image mounts nothing and holds no credential.
    runAsUser: 0
  # The host key is Ed25519 and generated per start, which costs milliseconds
  # rather than the seconds an RSA-4096 key costs -- so this budget is nothing
  # like the sftp profile's.
  startupProbe:
    tcpSocket:
      port: 2222
    periodSeconds: 2
    failureThreshold: 15
  livenessProbe:
    tcpSocket:
      port: 2222
    periodSeconds: 10
    timeoutSeconds: 3
    failureThreshold: 3
  resources:
    requests:
      cpu: 10m
      memory: 32Mi
    limits:
      # Headroom for `pg_dump`/`pg_restore`, which stream rather than buffer.
      memory: 256Mi
{{- end -}}
