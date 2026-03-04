# Matrix / Tuwunel Helm Chart

Custom Helm chart for deploying [Tuwunel](https://matrix-construct.github.io/tuwunel/) in Caelus.

## Design intent

- Single-replica `StatefulSet` with persistent storage for RocksDB data.
- One domain value (`serverName`) drives both ingress host and Matrix `server_name`.
- Federation is expected via HTTPS `:443` + `.well-known` endpoints (no explicit `8448` service).
- Curated config surface with `extraEnv` for advanced overrides.

## Quick test

```bash
helm lint ./charts/matrix
helm template matrix ./charts/matrix --set serverName=matrix.app.example.com
```

## Key values

| Value | Description | Default |
|---|---|---|
| `serverName` | Matrix homeserver name and ingress host | `matrix.example.com` |
| `image.repository` | Tuwunel image repository | `ghcr.io/matrix-construct/tuwunel` |
| `image.tag` | Tuwunel image tag | `v1.5.0` |
| `service.port` | Kubernetes Service port | `80` |
| `service.targetPort` | Tuwunel container listen port | `6167` |
| `ingress.enabled` | Enable ingress creation | `true` |
| `ingress.className` | Ingress class | `traefik` |
| `persistence.enabled` | Enable persistent data | `true` |
| `persistence.size` | Data PVC size | `10Gi` |
| `persistence.storageClassName` | StorageClass (`null` = cluster default) | `null` |
| `registration.token` | Static registration token | `""` |
| `registration.tokenSecretRef.*` | Existing secret reference for token | empty |
| `federation.enabled` | Enable federation behavior in Tuwunel | `true` |
| `trustedServers` | Notary trusted key servers | `["matrix.org"]` |
| `extraEnv` | Extra container env entries | `[]` |

## Registration behavior

Registration is enabled implicitly when either of these is set:

1. `registration.token`, or
2. `registration.tokenSecretRef.name` + `registration.tokenSecretRef.key`

If neither is set, registration remains closed.

When `registration.token` is set (and `tokenSecretRef.name` is empty), the chart
creates a Secret automatically.

Set only one source at a time: inline token or existing secret reference.

## Automatic well-known wiring

The chart always injects:

- `TUWUNEL_WELL_KNOWN__CLIENT=https://<serverName>`
- `TUWUNEL_WELL_KNOWN__SERVER=<serverName>:443`

This supports federation on a single hostname with TLS termination handled upstream.

## Package and Push (OCI)

Package the chart and push to the Caelus OCI registry:

```bash
cd charts/matrix
helm package .
helm registry login registry.home:80
helm push matrix-0.1.0.tgz oci://registry.home:80/helm --plain-http
```

Pull test:

```bash
helm pull oci://registry.home:80/helm/matrix --version 0.1.0 --plain-http
```
