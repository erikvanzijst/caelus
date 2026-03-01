# Mattermost Self-Contained Helm Chart

A wrapper Helm chart that bundles the official [mattermost-team-edition](https://github.com/mattermost/mattermost-helm/tree/master/charts/mattermost-team-edition) chart with the official [PostgreSQL](https://hub.docker.com/_/postgres) image to provide a fully self-contained deployment.

## Why This Chart?

The official Mattermost Helm chart no longer includes MySQL/PostgreSQL as a dependency (deprecated in Mattermost 11.x). This wrapper chart re-adds database dependency by combining:

- `mattermost-team-edition` - The official Mattermost Team Edition
- `postgresql` - Official PostgreSQL image for database storage

## Prerequisites

- Kubernetes cluster 1.20+
- Helm 3.13+
- Ingress controller (Traefik in Caelus)

## Build and Publish to OCI Registry

### Manual Steps

To build and publish this chart to your OCI registry (`registry.home:80/helm`):

```bash
# 1. Navigate to the chart directory
cd charts/mattermost

# 2. Add the required Helm repositories
helm repo add mattermost https://helm.mattermost.com
helm repo update

# 3. Download and extract dependencies
helm dependency build

# 4. Package the chart
helm package .

# 5. Push to OCI registry
# Note: You may need to login first: helm registry login registry.home:80
helm push mattermost-1.0.0.tgz oci://registry.home:80/helm --plain-http
```

### Verify the Chart

```bash
# List available versions
helm search repo registry.home:80/helm/mattermost --versions --plain-http

# Pull the chart to verify
helm pull oci://registry.home:80/helm/mattermost --version 1.0.0 --plain-http
```

## Installation

### Basic Installation

```bash
# Install with required values
# Only the host is required - PostgreSQL uses official defaults (postgres/postgres/postgres)
helm install mattermost oci://registry.home:80/helm/mattermost --plain-http \
  --version 1.0.0 \
  --namespace mattermost \
  --create-namespace \
  --set host=mm.app.deprutser.be
```

### Using a Values File

Create a `values.yaml`:

```yaml
host: mm.app.deprutser.be
```

**Note:** If your Helm/ci system doesn't support arrays, use a values file instead of `--set` flags.

Install:

```bash
helm install mattermost oci://registry.home:80/helm/mattermost \
  --plain-http \
  --version 1.0.0 \
  --namespace mattermost \
  -f values.yaml
```

## Values Reference

### Required Values

| Value | Description | Example |
|-------|-------------|---------|
| `host` | The hostname for Mattermost | `mm.app.deprutser.be` |

### Optional Values

#### Mattermost Configuration

| Value | Default | Description |
|-------|---------|-------------|
| `mattermost-team-edition.image.tag` | `11.4.2` | Mattermost image tag |
| `mattermost-team-edition.ingress.className` | `traefik` | Ingress class |
| `mattermost-team-edition.ingress.annotations` | `{}` | Ingress annotations |
| `mattermost-team-edition.ingress.tls` | `[]` | TLS configuration (empty = no TLS, handled by load balancer) |

#### PostgreSQL Configuration

| Value | Default | Description |
|-------|---------|-------------|
| `postgresql.image` | `postgres` | PostgreSQL image (official) |
| `postgresql.imageTag` | `18` | PostgreSQL version |
| `postgresql.username` | `postgres` | Database username |
| `postgresql.database` | `postgres` | Database name |
| `postgresql.password` | `postgres` | Database password |
| `postgresql.size` | `10Gi` | PVC size |

### Database Credentials

The chart uses PostgreSQL's official defaults:

- Username: `postgres`
- Password: `postgres`
- Database: `postgres`

The connection string is generated automatically:
```
postgres://postgres:postgres@{release-name}-postgresql:5432/postgres?sslmode=disable&connect_timeout=10
```

## Upgrading

When upgrading the chart, update the `values.yaml` with new versions:

```bash
helm upgrade mattermost oci://registry.home:80/helm/mattermost \
  --plain-http \
  --version NEW_VERSION \
  --namespace mattermost \
  -f values.yaml
```

## Uninstalling

```bash
helm uninstall mattermost --namespace mattermost
# Note: PVCs may need to be manually deleted for complete cleanup
kubectl delete pvc -n mattermost -l app.kubernetes.io/instance=mattermost
```

## Chart Versions

| Chart Version | Mattermost Version | PostgreSQL Version |
|---------------|-------------------|-------------------|
| 1.0.0 | 11.4.2 | 18 (official) |

## Architecture

```
┌─────────────────────────────────────────┐
│           mattermost namespace          │
│  ┌───────────────────────────────────┐  │
│  │     mattermost-team-edition       │  │
│  │         (Deployment)              │  │
│  └──────────────┬────────────────────┘  │
│                 │                       │
│                 ▼                       │
│  ┌───────────────────────────────────┐  │
│  │      PostgreSQL (StatefulSet)     │  │
│  │       postgres:18 (official)      │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Limitations

- Single replica deployment only
- Uses fixed PostgreSQL credentials (postgres/postgres/postgres) - suitable for development/testing
- Storage is tied to the release lifecycle
