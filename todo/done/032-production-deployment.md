# Production Deployment Plan

**Last Updated**: 2026-02-27  
**Target Base URL**: https://app.deprutser.be  
**Container Registry**: ghcr.io  
**Kubernetes Cluster**: dev-k3s (kubeconfig at `k8s/kubeconfigs/dev-k3s.yaml`)

---

## Overview

This document outlines the complete deployment pipeline for the Caelus monorepo, consisting of:
- **api/**: FastAPI + SQLModel backend service
- **ui/**: React + TypeScript + Vite frontend

The deployment architecture uses:
- Two separate container images (api, ui) served from ghcr.io
- Kubernetes for orchestration
- Nginx ingress with path-based routing (`/api` → api, all else → ui)
- PostgreSQL database running in-cluster
- Terraform for infrastructure management

---

## Phase 0: Add `/api` Prefix to API Server

**Priority**: CRITICAL - This is the foundational change that enables clean ingress routing.

### Why This Matters

Currently:
- UI makes API calls to absolute URLs like `http://localhost:8000`
- API serves all endpoints at root (`/users`, `/products`, etc.)

With path-based ingress:
- UI should call relative URLs like `/api/users`
- Ingress routes `/api/*` → API service, `/*` → UI service
- This allows both services to share the same hostname

### 0.1 UI Changes

#### File: `ui/src/api/client.ts`

**Current code:**
```typescript
const envUrl = import.meta.env.VITE_API_URL as string | undefined

export const API_URL = envUrl ?? 'http://localhost:8000'
```

**Required change:**
```typescript
const envUrl = import.meta.env.VITE_API_URL as string | undefined

// Use relative /api in production, fallback to localhost:8000 for local dev
export const API_URL = envUrl ?? '/api'
```

This change:
- Allows production UI to make requests to `/api/users`, `/api/products`, etc.
- Maintains local dev experience (VITE_API_URL=http://localhost:8000)
- Enables single static build for all environments

#### File: `ui/.env.production`

Create this file with production defaults:

```bash
VITE_API_URL=/api
```

This ensures that when `npm run build` runs for production, the default API_URL is `/api`.

#### File: `ui/vite.config.ts`

Verify or add base configuration:

```typescript
export default defineConfig({
  base: '/',  // Required for serving at domain root
  plugins: [react()],
  // ... rest of config
})
```

### 0.2 API Changes

#### File: `api/app/main.py`

**Current code:**
```python
app.include_router(users.router)
app.include_router(products.router)
```

**Required change:**
```python
app.include_router(users.router, prefix="/api")
app.include_router(products.router, prefix="/api")
```

**Why this works:**
- FastAPI's `APIRouter` accepts a `prefix` parameter
- All routes in that router get the prefix prepended
- This changes `/users` → `/api/users`, `/products` → `/api/products`

#### Move OpenAPI Docs to `/api` Prefix

The API documentation (Swagger UI and ReDoc) must also move under the `/api` prefix for consistency. Update `api/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI(
    title="Caelus Deploy",
    description="Service for provisioning user-owned webapp instances on cloud infrastructure",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

@app.get("/docs", include_in_schema=False)
def redirect_to_docs() -> RedirectResponse:
    """Redirect /docs to /api/docs for backwards compatibility."""
    return RedirectResponse(url="/api/docs")

@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect root URL to Swagger UI docs."""
    return RedirectResponse(url="/api/docs")
```

**Key decisions:**
- `docs_url="/api/docs"`: Swagger UI at `/api/docs`
- `redoc_url="/api/redoc"`: ReDoc at `/api/redoc`  
- `openapi_url="/api/openapi.json"`: OpenAPI schema at `/api/openapi.json`
- Added `/docs` redirect: Maintains backwards compatibility for developers who bookmark `/docs`
- Updated root redirect: Root URL now points to `/api/docs`

### 0.3 Verification Checklist

After these changes:
- [ ] API endpoints are: `/api/users`, `/api/users/{id}`, `/api/products`, `/api/products/{id}`
- [ ] UI calls `/api/*` paths
- [ ] Local dev still works: `VITE_API_URL=http://localhost:8000 npm run dev`
- [ ] API docs (Swagger UI) accessible at `/api/docs`
- [ ] ReDoc accessible at `/api/redoc`
- [ ] OpenAPI schema at `/api/openapi.json`

### 0.4 CORS Consideration

The API's CORS configuration in `api/app/main.py` currently allows:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production, the UI will be served from `https://app.deprutser.be`. Update to:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "https://app.deprutser.be"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Phase 1: Dockerfiles

### Architecture Decision: Multi-Stage Builds

We use multi-stage builds to:
- Keep final images small (no build tools, source code, or package managers)
- Minimize attack surface
- Ensure reproducible builds

### 1.1 api/Dockerfile

**Location**: `api/Dockerfile`

```dockerfile
# =============================================================================
# Stage 1: Build dependencies
# =============================================================================
FROM python:3.11-slim AS builder

# Install uv for fast dependency management
RUN pip install uv

WORKDIR /app

# Copy only dependency files first (for layer caching)
COPY pyproject.toml .

# Sync dependencies into isolated virtual environment
# --no-dev: exclude dev dependencies (pytest, typer, etc.)
# --frozen: fail if lock file doesn't match (reproducible builds)
RUN uv sync --no-dev --frozen

# =============================================================================
# Stage 2: Production runtime
# =============================================================================
FROM python:3.11-slim

# Install uv (needed to run the venv) and create non-root user
RUN pip install uv && \
    useradd -m -u 1000 appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv .venv

# Copy application source
COPY app/ app/

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user for security
USER appuser

# Expose the port uvicorn will listen on
EXPOSE 8000

# Health check for kubernetes
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/docs')" || exit 1

# Run uvicorn with production settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Key decisions:**
- Python 3.11-slim: Minimal base image (~150MB vs ~900MB for full)
- `uv sync` instead of `pip install`: Much faster, handles complex dependencies better
- Non-root user: Security best practice
- Health check: Enables Kubernetes liveness probes
- 4 workers: Production-ready concurrency

### 1.2 ui/Dockerfile

**Location**: `ui/Dockerfile`

```dockerfile
# =============================================================================
# Stage 1: Build React application
# =============================================================================
FROM node:20-alpine AS builder

# Install pnpm for faster, more reliable installs (optional - npm also works)
# Using npm for simplicity as it's already in package.json
RUN corepack enable

WORKDIR /app

# Copy dependency files first (layer caching)
COPY package*.json ./

# Install all dependencies (including devDependencies needed for build)
RUN npm ci

# Copy source code
COPY .. .

# Build production bundle
# This creates optimized static files in dist/
RUN npm run build

# =============================================================================
# Stage 2: Serve with nginx
# =============================================================================
FROM nginx:alpine

# Copy built static files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration for SPA routing and API proxying
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Run nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
```

**Key decisions:**
- Node 20 Alpine: Minimal Node image for building
- `npm ci`: Faster and more reliable than npm install (uses package-lock.json)
- nginx: Industry standard for serving static content
- Alpine base: Very small (~15MB)

### 1.3 ui/nginx.conf

**Location**: `ui/nginx.conf`

**Note**: This nginx only serves static UI files. API requests are routed by the Kubernetes Ingress before reaching this container, so no proxy configuration is needed here.

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # =========================================================================
    # SPA Routing: Serve index.html for all non-file routes
    # =========================================================================
    location / {
        try_files $uri $uri/ /index.html;
    }

    # =========================================================================
    # Static assets: Long cache expiration
    # =========================================================================
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # =========================================================================
    # Security headers
    # =========================================================================
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
}
```

**Key decisions:**
- SPA fallback: `try_files $uri $uri/ /index.html` handles client-side routing
- No API proxy needed: Ingress routes `/api/*` directly to API service
- Caching: Static assets get 1-year cache with immutable flag
- Security headers: Basic hardening

### 1.4 .dockerignore Files

Create `.dockerignore` in both `api/` and `ui/` roots to prevent unnecessary files from being copied into builds.

#### File: `api/.dockerignore`

```
# Git
.git
.gitignore

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.eggs/
*.egg-info/
*.egg

# Virtual environments
.venv/
venv/
ENV/

# Testing
.pytest_cache/
.coverage
htmlcov/

# IDEs
.idea/
.vscode/
*.swp
*.swo

# Build artifacts
dist/
build/

# Documentation
*.md
docs/

# Terraform (in case someone runs from root)
tf/
*.tf
*.tfvars

# CI/CD
.github/
.gitlab-ci.yml

# Misc
.DS_Store
*.log
.env
.env.*
```

#### File: `ui/.dockerignore`

```
# Git
.git
.gitignore

# Dependencies
node_modules/

# Build output
dist/

# Testing
coverage/

# IDEs
.idea/
.vscode/
*.swp
*.swo

# Misc
.DS_Store
*.log

# API (we don't need api code in ui build)
../api/
```

### 1.5 Build and Test Dockerfiles

Before proceeding, verify Dockerfiles work:

```bash
# Test API build
docker build -t caelus-api:local ./api

# Test UI build
docker build -t caelus-ui:local ./ui

# Run locally to verify
docker run -p 8000:8000 caelus-api:local
docker run -p 80:80 caelus-ui:local
```

---

## Phase 2: Build & Push Script

**Purpose**: Automate building both images and pushing to the container registry.

**Location**: `scripts/build-images.sh`

```bash
#!/bin/bash
#
# Build and push production container images to ghcr.io
#
# Usage:
#   ./scripts/build-images.sh           # Builds with git SHA tag
#   ./scripts/build-images.sh v1.2.3    # Builds with custom tag
#

set -euo pipefail

# Configuration
REGISTRY=ghcr.io/$(gh repo view --json owner -q .owner.login)/caelus

# Determine tag: use argument or git SHA
if [ -n "${1:-}" ]; then
    TAG="$1"
else
    TAG=$(git rev-parse --short HEAD)
fi

echo "=============================================="
echo "Building Caelus Images"
echo "Registry: ${REGISTRY}"
echo "Tag: ${TAG}"
echo "=============================================="

# -----------------------------------------------------------------------------
# Build API image
# -----------------------------------------------------------------------------
echo ""
echo "[1/4] Building API image..."
docker build \
    --tag "${REGISTRY}-api:${TAG}" \
    --tag "${REGISTRY}-api:latest" \
    ./api

# -----------------------------------------------------------------------------
# Build UI image
# -----------------------------------------------------------------------------
echo ""
echo "[2/4] Building UI image..."
docker build \
    --tag "${REGISTRY}-ui:${TAG}" \
    --tag "${REGISTRY}-ui:latest" \
    ./ui

# -----------------------------------------------------------------------------
# Push to registry
# -----------------------------------------------------------------------------
echo ""
echo "[3/4] Pushing API image..."
docker push "${REGISTRY}-api:${TAG}"
docker push "${REGISTRY}-api:latest"

echo ""
echo "[4/4] Pushing UI image..."
docker push "${REGISTRY}-ui:${TAG}"
docker push "${REGISTRY}-ui:latest"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "Build Complete!"
echo "=============================================="
echo "Images pushed:"
echo "  ${REGISTRY}-api:${TAG}"
echo "  ${REGISTRY}-api:latest"
echo "  ${REGISTRY}-ui:${TAG}"
echo "  ${REGISTRY}-ui:latest"
echo ""
```

Make it executable:

```bash
chmod +x scripts/build-images.sh
```

**Key decisions:**
- Uses `gh repo view` to automatically determine org/user from current repo
- Tags with both git SHA (for traceability) and `latest`
- Uses `set -euo pipefail` for strict error handling
- Works with any registry (just change REGISTRY variable)

---

## Phase 3: Terraform Project

### 3.1 Directory Structure

```
tf/
├── main.tf                 # Main configuration (imports all modules)
├── variables.tf           # Input variables
├── outputs.tf              # Output values
├── providers.tf            # Provider configuration
├── terraform.tfvars        # Default values (non-sensitive)
├── secrets.auto.tfvars     # Secrets (gitignored!)
├── .gitignore              # Git ignore rules
└── k8s/
    ├── namespace.tf        # Kubernetes namespace
    ├── configmap.tf        # Non-sensitive config
    ├── secrets.tf          # Sensitive data
    ├── postgres.tf         # PostgreSQL deployment
    ├── deployment-api.tf  # API deployment
    ├── deployment-ui.tf   # UI deployment
    ├── service-api.tf     # API service
    ├── service-ui.tf      # UI service
    └── ingress.tf          # Ingress routing
```

### 3.2 Provider Configuration

**File**: `tf/providers.tf`

```terraform
terraform {
  required_version = ">= 1.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "kubernetes" {
  config_path = "../k8s/kubeconfigs/dev-k3s.yaml"
  
  # Optional: Enable experimental features if needed
  experiments {
    manifest_resource = true
  }
}
```

**Key decisions:**
- Uses kubeconfig at `../k8s/kubeconfigs/dev-k3s.yaml` as specified
- Version constraints ensure compatibility
- Random provider for generating passwords if needed

### 3.3 Variables

**File**: `tf/variables.tf`

```terraform
variable "api_image" {
  description = "API container image (including registry and tag)"
  type        = string
  default     = "ghcr.io/<org>/caelus-api:latest"
}

variable "ui_image" {
  description = "UI container image (including registry and tag)"
  type        = string
  default     = "ghcr.io/<org>/caelus-ui:latest"
}

variable "namespace" {
  description = "Kubernetes namespace for all resources"
  type        = string
  default     = "caelus"
}

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "caelus"
}

variable "db_user" {
  description = "Postgres username"
  type        = string
  default     = "caelus"
}

variable "db_password" {
  description = "Postgres password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}

variable "domain" {
  description = "External domain for ingress"
  type        = string
  default     = "app.deprutser.be"
}

variable "api_replicas" {
  description = "Number of API pod replicas"
  type        = number
  default     = 2
}

variable "ui_replicas" {
  description = "Number of UI pod replicas"
  type        = number
  default     = 2
}
```

### 3.4 Outputs

**File**: `tf/outputs.tf`

```terraform
output "namespace" {
  description = "Kubernetes namespace"
  value       = kubernetes_namespace.main.metadata[0].name
}

output "api_service_name" {
  description = "API Kubernetes service name"
  value       = kubernetes_service.api.metadata[0].name
}

output "ui_service_name" {
  description = "UI Kubernetes service name"
  value       = kubernetes_service.ui.metadata[0].name
}

output "ingress_host" {
  description = "External hostname"
  value       = var.domain
}

output "api_endpoint" {
  description = "Full API endpoint URL"
  value       = "https://${var.domain}/api"
}
```

### 3.5 Terraform Defaults

**File**: `tf/terraform.tfvars`

```hcl
api_image = "ghcr.io/<org>/caelus-api:latest"
ui_image  = "ghcr.io/<org>/caelus-ui:latest"
namespace = "caelus"
domain    = "app.deprutser.be"
```

### 3.6 Secrets (Gitignored)

**File**: `tf/secrets.auto.tfvars`

```hcl
# IMPORTANT: This file contains secrets. Do NOT commit to version control!
# Add to .gitignore: tf/secrets.auto.tfvars

db_password = "CHANGE_ME_TO_SECURE_PASSWORD"
```

**File**: `tf/.gitignore`

```
# Terraform
.terraform/
*.tfstate
*.tfstate.backup
*.tfstate.*.backup

# Secrets - NEVER commit these!
secrets.auto.tfvars
secrets.tfvars

# Local values
.terraform.lock.hcl
```

### 3.7 Namespace

**File**: `tf/k8s/namespace.tf`

```terraform
resource "kubernetes_namespace" "main" {
  metadata {
    name = var.namespace
    
    labels = {
      name = var.namespace
      environment = "production"
    }
  }
}
```

### 3.8 ConfigMap

**File**: `tf/k8s/configmap.tf`

```terraform
resource "kubernetes_config_map" "api" {
  metadata {
    name      = "caelus-api-config"
    namespace = var.namespace
  }

  data = {
    DATABASE_URL     = "postgresql://${var.db_user}:${var.db_password}@caelus-postgres:5432/${var.db_name}"
    LOG_LEVEL        = "info"
    PYTHONUNBUFFERED = "1"
  }

  depends_on = [kubernetes_namespace.main]
}
```

### 3.9 Secrets

**File**: `tf/k8s/secrets.tf`

```terraform
resource "kubernetes_secret" "db" {
  metadata {
    name      = "caelus-db"
    namespace = var.namespace
  }

  type = "Opaque"

  data = {
    username = var.db_user
    password = var.db_password
    database = var.db_name
  }

  depends_on = [kubernetes_namespace.main]
}
```

### 3.10 PostgreSQL Deployment

**File**: `tf/k8s/postgres.tf`

```terraform
resource "kubernetes_deployment" "postgres" {
  metadata {
    name      = "caelus-postgres"
    namespace = var.namespace
    labels = {
      app = "caelus-postgres"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "caelus-postgres"
      }
    }

    strategy {
      type = "Recreate"
    }

    template {
      metadata {
        labels = {
          app = "caelus-postgres"
        }
      }

      spec {
        container {
          image = "postgres:16-alpine"
          name  = "postgres"

          env {
            name  = "POSTGRES_DB"
            value = var.db_name
          }

          env {
            name  = "POSTGRES_USER"
            value = var.db_user
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = "caelus-db"
                key  = "password"
              }
            }
          }

          port {
            name           = "postgres"
            container_port = 5432
            protocol       = "TCP"
          }

          volume_mount {
            name       = "postgres-data"
            mount_path = "/var/lib/postgresql/data"
          }

          resources {
            requests = {
              memory = "256Mi"
              cpu    = "250m"
            }
            limits = {
              memory = "512Mi"
              cpu    = "500m"
            }
          }

          liveness_probe {
            exec {
              command = ["pg_isready", "-U", var.db_user]
            }
            initial_delay_seconds = 30
            period_seconds         = 10
            timeout_seconds        = 5
            failure_threshold      = 3
          }

          readiness_probe {
            exec {
              command = ["pg_isready", "-U", var.db_user]
            }
            initial_delay_seconds = 5
            period_seconds        = 5
            timeout_seconds        = 3
            failure_threshold      = 3
          }
        }

        volume {
          name = "postgres-data"
          
          empty_dir {}
          # For production, use:
          # persistent_volume_claim {
          #   claim_name = "caelus-postgres-pvc"
          # }
        }
      }
    }
  }

  depends_on = [kubernetes_namespace.main, kubernetes_secret.db]
}
```

**Service**:

```terraform
resource "kubernetes_service" "postgres" {
  metadata {
    name      = "caelus-postgres"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "caelus-postgres"
    }

    port {
      name       = "postgres"
      port       = 5432
      target_port = "postgres"
    }

    cluster_ip = "None"  # Headless service for pod DNS
  }

  depends_on = [kubernetes_namespace.main]
}
```

**Key decisions:**
- `cluster_ip = "None"` creates a headless service - pods get individual DNS records
- Resource limits prevent runaway resource usage
- Health checks ensure reliability
- empty_dir for data (non-persistent for dev) - production should use PVC

### 3.11 API Deployment

**File**: `tf/k8s/deployment-api.tf`

```terraform
resource "kubernetes_deployment" "api" {
  metadata {
    name      = "caelus-api"
    namespace = var.namespace
    labels = {
      app = "caelus-api"
    }
  }

  spec {
    replicas = var.api_replicas

    selector {
      match_labels = {
        app = "caelus-api"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = 1
        max_unavailable = 0
      }
    }

    template {
      metadata {
        labels = {
          app = "caelus-api"
        }
      }

      spec {
        container {
          image = var.api_image
          name  = "api"

          port {
            name           = "http"
            container_port = 8000
            protocol       = "TCP"
          }

          env_from {
            config_map_ref {
              name = "caelus-api-config"
            }
          }

          env_from {
            secret_ref {
              name = "caelus-db"
            }
          }

          resources {
            requests = {
              memory = "256Mi"
              cpu    = "250m"
            }
            limits = {
              memory = "512Mi"
              cpu    = "500m"
            }
          }

          liveness_probe {
            http_get {
              path = "/docs"
              port = "http"
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            timeout_seconds        = 5
            failure_threshold      = 3
          }

          readiness_probe {
            http_get {
              path = "/docs"
              port = "http"
            }
            initial_delay_seconds = 5
            period_seconds        = 5
            timeout_seconds        = 3
            failure_threshold      = 3
          }
        }
      }
    }
  }

  depends_on = [kubernetes_namespace.main]
}
```

### 3.12 UI Deployment

**File**: `tf/k8s/deployment-ui.tf`

```terraform
resource "kubernetes_deployment" "ui" {
  metadata {
    name      = "caelus-ui"
    namespace = var.namespace
    labels = {
      app = "caelus-ui"
    }
  }

  spec {
    replicas = var.ui_replicas

    selector {
      match_labels = {
        app = "caelus-ui"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = 1
        max_unavailable = 0
      }
    }

    template {
      metadata {
        labels = {
          app = "caelus-ui"
        }
      }

      spec {
        container {
          image = var.ui_image
          name  = "ui"

          port {
            name           = "http"
            container_port = 80
            protocol       = "TCP"
          }

          resources {
            requests = {
              memory = "64Mi"
              cpu    = "100m"
            }
            limits = {
              memory = "128Mi"
              cpu    = "200m"
            }
          }

          liveness_probe {
            http_get {
              path = "/"
              port = "http"
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            timeout_seconds        = 5
            failure_threshold      = 3
          }

          readiness_probe {
            http_get {
              path = "/"
              port = "http"
            }
            initial_delay_seconds = 5
            period_seconds        = 5
            timeout_seconds        = 3
            failure_threshold      = 3
          }
        }
      }
    }
  }

  depends_on = [kubernetes_namespace.main]
}
```

### 3.13 Services

**File**: `tf/k8s/service-api.tf`

```terraform
resource "kubernetes_service" "api" {
  metadata {
    name      = "caelus-api"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "caelus-api"
    }

    port {
      name       = "http"
      port       = 8000
      target_port = "http"
    }

    type = "ClusterIP"
  }

  depends_on = [kubernetes_namespace.main]
}
```

**File**: `tf/k8s/service-ui.tf`

```terraform
resource "kubernetes_service" "ui" {
  metadata {
    name      = "caelus-ui"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "caelus-ui"
    }

    port {
      name       = "http"
      port       = 80
      target_port = "http"
    }

    type = "ClusterIP"
  }

  depends_on = [kubernetes_namespace.main]
}
```

### 3.14 Ingress

**File**: `tf/k8s/ingress.tf`

```terraform
resource "kubernetes_ingress" "main" {
  metadata {
    name      = "caelus-ingress"
    namespace = var.namespace
    
    annotations = {
      "kubernetes.io/ingress.class"                    = "nginx"
      "nginx.ingress.kubernetes.io/rewrite-target"    = "/"
      "nginx.ingress.kubernetes.io/proxy-read-timeout" = "60"
      "nginx.ingress.kubernetes.io/proxy-send-timeout" = "60"
    }
  }

  spec {
    ingress_class_name = "nginx"

    rule {
      host = var.domain

      http {
        # API routes - must come first for prefix matching
        path {
          path      = "/api"
          path_type = "Prefix"

          backend {
            service {
              name = "caelus-api"
              port {
                number = 8000
              }
            }
          }
        }

        # UI - catches all other routes (including /)
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = "caelus-ui"
              port {
                number = 80
              }
            }
          }
        }
      }
    }

    # TLS configuration (optional - for production with real certs)
    # tls {
    #   hosts = [var.domain]
    #   secret_name = "caelus-tls"
    # }
  }

  depends_on = [
    kubernetes_namespace.main,
    kubernetes_service.api,
    kubernetes_service.ui
  ]
}
```

**Key decisions:**
- `/api` path first: Ingress matches in order, so more specific paths must come first
- `rewrite-target = "/"`: Strips the matched prefix from the request (but we handle this in nginx.conf instead)
- For production TLS: Use cert-manager with Let's Encrypt (not included in this base config)

### 3.15 Main.tf (Orchestration)

**File**: `tf/main.tf`

```terraform
# This file brings together all Kubernetes resources
# Resources are defined in individual files under k8s/

terraform {
  required_version = ">= 1.0"
}

# Include all k8s resources
# The depends_on in each resource file ensures proper ordering

# Namespace must be created first
resource "null_resource" "wait_for_namespace" {
  provisioner "local-exec" {
    command = "echo 'Namespace created by k8s/namespace.tf'"
  }
}
```

Actually, it's simpler to just put all `.tf` files in `tf/k8s/` and reference them. Let's restructure:

```
tf/
├── main.tf                 # Just calls modules or includes
├── providers.tf
├── variables.tf
├── outputs.tf
├── k8s/                    # All k8s resources
│   ├── namespace.tf
│   ├── configmap.tf
│   ├── secrets.tf
│   ├── postgres.tf
│   ├── deployment-api.tf
│   ├── deployment-ui.tf
│   ├── service-api.tf
│   ├── service-ui.tf
│   └── ingress.tf
└── ...
```

The resources already have proper `depends_on` chains, so Terraform will handle ordering correctly.

### 3.16 Terraform Workflow

```bash
# Navigate to terraform directory
cd tf

# Initialize (downloads providers)
terraform init

# Review planned changes
terraform plan -var-file=secrets.auto.tfvars

# Apply (creates all resources)
terraform apply -var-file=secrets.auto.tfvars

# Later: update images without recreating infrastructure
terraform apply -var-file=secrets.auto.tfvars -var="api_image=ghcr.io/<org>/caelus-api:v1.2.3"

# Destroy (careful!)
terraform destroy -var-file=secrets.auto.tfvars
```

---

## Phase 4: GitHub Actions

### 4.1 Workflow File

**Location**: `.github/workflows/deploy.yaml`

```yaml
name: Build and Push Production Images

on:
  push:
    branches:
      - main

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      # -------------------------------------------------------------------------
      # Setup
      # -------------------------------------------------------------------------
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      # -------------------------------------------------------------------------
      # Login to container registry
      # -------------------------------------------------------------------------
      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # -------------------------------------------------------------------------
      # Extract metadata for tags
      # -------------------------------------------------------------------------
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=sha,prefix=
            type=raw,value=latest,enable={{is_default_branch}}

      # -------------------------------------------------------------------------
      # Build and push API image
      # -------------------------------------------------------------------------
      - name: Build and push API
        uses: docker/build-push-action@v5
        with:
          context: ./api
          push: true
          tags: |
            ${{ steps.meta.outputs.tags }}-api
            ${{ steps.meta.outputs.tags }}-api-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64

      # -------------------------------------------------------------------------
      # Build and push UI image
      # -------------------------------------------------------------------------
      - name: Build and push UI
        uses: docker/build-push-action@v5
        with:
          context: ./ui
          push: true
          tags: |
            ${{ steps.meta.outputs.tags }}-ui
            ${{ steps.meta.outputs.tags }}-ui-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64

      # -------------------------------------------------------------------------
      # Summary
      # -------------------------------------------------------------------------
      - name: Summary
        run: |
          echo "## Build Complete" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "Images pushed:" >> $GITHUB_STEP_SUMMARY
          echo "- \`${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-api:${{ github.sha }}\`" >> $GITHUB_STEP_SUMMARY
          echo "- \`${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-ui:${{ github.sha }}\`" >> $GITHUB_STEP_SUMMARY
          echo "- \`${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-api:latest\`" >> $GITHUB_STEP_SUMMARY
          echo "- \`${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-ui:latest\`" >> $GITHUB_STEP_SUMMARY
```

### 4.2 Required Secrets

To use this workflow, you'll need to:

1. **GITHUB_TOKEN**: Automatically available in GitHub Actions (no setup needed)
2. **packages:write**: The GITHUB_TOKEN doesn't have packages write permission by default. You need to:
   - Create a Personal Access Token (PAT) with `packages:write` scope
   - Add it as a repository secret (e.g., `GITHUB_TOKEN` with the PAT value)
   - Or use a GitHub App with packages permissions

### 4.3 Workflow Triggers

Currently configured to run on every push to `main`. Alternative strategies:

```yaml
# Option A: On every push to main
on:
  push:
    branches:
      - main

# Option B: On tags (releases)
on:
  push:
    tags:
      - 'v*'

# Option C: On push AND on tags
on:
  push:
    branches:
      - main
    tags:
      - 'v*'
```

### 4.4 Multi-Platform Builds

The workflow includes `platforms: linux/amd64,linux/arm64` for cross-platform compatibility. This requires:
- QEMU to be set up (docker/setup-buildx-action handles this)
- Longer build times initially
- More storage for image layers

For simpler setup, remove the `platforms` line.

---

## Implementation Order

1. **Phase 0**: Add `/api` prefix to API (UI + API changes)
   - Verify local dev still works
   
2. **Phase 1**: Dockerfiles
   - Create api/Dockerfile
   - Create ui/Dockerfile
   - Create ui/nginx.conf
   - Create .dockerignore files
   - Test builds locally
   
3. **Phase 2**: Build script
   - Create scripts/build-images.sh
   - Test pushing to ghcr.io
   
4. **Phase 3**: Terraform
   - Create tf/ directory structure
   - Create all .tf files
   - Test with `terraform init` and `plan`
   
5. **Phase 4**: GitHub Actions
   - Create .github/workflows/deploy.yaml
   - Verify workflow runs on push to main

---

## Verification Checklist

### Phase 0 - API Prefix
- [ ] `ui/src/api/client.ts` uses `/api` as default
- [ ] `ui/.env.production` exists with `VITE_API_URL=/api`
- [ ] `api/app/main.py` includes routers with `prefix="/api"`
- [ ] CORS updated to allow production domain
- [ ] Local dev works (`VITE_API_URL=http://localhost:8000 npm run dev`)

### Phase 1 - Dockerfiles
- [ ] `api/Dockerfile` builds successfully
- [ ] `ui/Dockerfile` builds successfully
- [ ] `ui/nginx.conf` configured for SPA + API proxy
- [ ] `.dockerignore` files created in both directories

### Phase 2 - Build Script
- [ ] `scripts/build-images.sh` is executable
- [ ] Script successfully pushes to ghcr.io

### Phase 3 - Terraform
- [ ] `tf/` directory created with all .tf files
- [ ] `secrets.auto.tfvars` configured
- [ ] `terraform init` succeeds
- [ ] `terraform plan` shows expected resources
- [ ] `terraform apply` creates all resources
- [ ] Services accessible within cluster
- [ ] Ingress routes correctly

### Phase 4 - GitHub Actions
- [ ] `.github/workflows/deploy.yaml` created
- [ ] Workflow runs on push to main
- [ ] Images pushed to ghcr.io with correct tags

---

## Post-Deployment Considerations

### Production Hardening

1. **TLS/HTTPS**
   - Install cert-manager: `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml`
   - Add TLS to ingress configuration
   - Use Let's Encrypt for automatic certificate renewal

2. **Database Persistence**
   - Replace `empty_dir` volumes with PersistentVolumeClaims
   - Consider managed PostgreSQL (RDS, Cloud SQL) for production

3. **Resource Tuning**
   - Monitor actual memory/CPU usage
   - Adjust resource requests/limits accordingly
   - Consider Horizontal Pod Autoscaler (HPA)

4. **Monitoring**
   - Add logging (ELK, Loki)
   - Add metrics (Prometheus + Grafana)
   - Set up alerts

5. **Backup**
   - Regular database backups
   - Test restore procedures

### Rollback Procedure

If deployment fails:

```bash
# Rollback to previous image version
terraform apply -var="api_image=ghcr.io/<org>/caelus-api:<previous-sha>"

# Or use kubectl directly for faster rollback
kubectl set image deployment/caelus-api api=ghcr.io/<org>/caelus-api:<sha>
kubectl set image deployment/caelus-ui ui=ghcr.io/<org>/caelus-ui:<sha>
```

---

## Appendix: File Summary

### New Files to Create

```
api/Dockerfile                    # Multi-stage Python build
api/.dockerignore                 # Exclude unnecessary files from build
ui/Dockerfile                     # Multi-stage Node→Nginx build
ui/.dockerignore                  # Exclude unnecessary files from build
ui/nginx.conf                     # SPA routing + API proxy
scripts/build-images.sh           # Build and push script
tf/main.tf                        # Terraform entry
tf/variables.tf                   # Input variables
tf/outputs.tf                     # Output values
tf/providers.tf                   # Provider config
tf/terraform.tfvars               # Non-sensitive defaults
tf/secrets.auto.tfvars            # Secrets (gitignored!)
tf/.gitignore                     # Git ignore rules
tf/k8s/namespace.tf               # Kubernetes namespace
tf/k8s/configmap.tf               # ConfigMap
tf/k8s/secrets.tf                 # Secrets
tf/k8s/postgres.tf                # PostgreSQL deployment + service
tf/k8s/deployment-api.tf          # API deployment
tf/k8s/deployment-ui.tf           # UI deployment
tf/k8s/service-api.tf            # API service
tf/k8s/service-ui.tf             # UI service
tf/k8s/ingress.tf                # Ingress routing
.github/workflows/deploy.yaml    # CI/CD workflow
```

### Files to Modify

```
ui/src/api/client.ts              # Change default API_URL
ui/app/main.py                    # Add CORS origin
api/app/main.py                   # Add router prefixes
```

### Files to Create

```
ui/.env.production                # Production environment defaults
```

---

**End of Production Deployment Plan**
