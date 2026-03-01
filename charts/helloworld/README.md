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
  --set ingress.className=traefik \
  --set ingress.host=hello.example.com \
  --set user.message="Hello from values"
```

## Publish to docker registry

```bash
helm lint ./k8s/hello-static-chart
helm package ./k8s/hello-static-chart --destination ./build
helm push ./build/hello-static-0.1.1.tgz oci://registry.home:80/helm --plain-http
```

Optionally pull to verify: `helm pull oci://registry.home:80/helm/hello-static --version 0.1.1 --plain-http --destination /tmp`

## Deploy to k3s

```bash
helm install hello-static oci://registry.home:80/helm/hello-static \
  --kubeconfig ./kubeconfigs/k3s-dev.yaml \
  --version 0.1.1 \
  --namespace hello2 \
  --create-namespace \
  --plain-http \
  --set ingress.host=hello2.app.deprutser.be
```