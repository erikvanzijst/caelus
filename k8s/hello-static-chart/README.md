# hello-static-chart

Demo Helm chart for Caelus architecture work.

## What it deploys

- PVC for persistent data
- Deployment with:
  - init container writing `/data/index.html` from `.Values.user.message`
  - nginx serving that file from PVC
- Service
- Optional Ingress

## Quick test

```bash
helm template demo ./k8s/hello-static-chart \
  --set ingress.enabled=true \
  --set ingress.host=hello.example.com \
  --set user.message="Hello from values"
```
