# custom

A generic chart for a **user-supplied application**. Every other product in this
repo pins its image: `vaultwarden/server:1.37.1` is a platform decision, and the
tenant only picks a hostname and a few settings. Here the tenant picks the image
too — it is whatever they built — and the chart's job is to run it without
letting them run somebody else's.

Unlike the curated products, this one is **database-managed**: there is no
`products/catalog/custom.yaml`, because the build subsystem that feeds it is still
being iterated on and pinning it to a rollout-reconciled catalog file would
freeze decisions that are not settled. The product, template, and plan rows are
seeded by hand — see [Caelus product template](#caelus-product-template) for the
values to paste.

## What it deploys

| Component | Object(s) |
|-----------|-----------|
| Application | Deployment `<release>-app` running the user's image, or the placeholder while none exists |
| Service | `<release>-app` `:80` → the container's `http` port |
| Ingress | `<release>-ingress` (per-deployment TLS via `caelus.ingress.tls`), only once the reconciler injects a hostname |

No PVC: an image built from a user's source tree is stateless as far as this
chart is concerned. Persistence, if it is ever offered here, is a separate
decision that should not be smuggled in as a default.

## The image contract

The tenant supplies a single string:

```
image: "{user_id}@{digest}"     # e.g. "5@sha256:4777d0…" — 64 lowercase hex chars
```

That is a real image reference with **the registry host stripped off**: the
repository is the owner's own user id. So composing the pull reference is just a
prefix:

```
{registry}/{user_id}@{digest}
```

`5@sha256:4777d0…` under `registry.home` becomes
`registry.home/5@sha256:4777d0…`. The chart still splits on `@` — but only to
police the two halves, not to reassemble them. Digests and repository paths
cannot contain `@`, so the split is unambiguous.

Withholding the registry host is deliberate, and so is verifying rather than
trusting the `{user_id}` repository. Together they are what make the ownership
assertion below meaningful: a tenant can neither point at an arbitrary registry
nor claim someone else's repository.

**Port: bind `0.0.0.0:$PORT`.** The chart injects `PORT` into the container,
set from the `containerPort` system value (default `8080`), and the Service
targets that same port. The platform hands the app its port rather than the app
being required to know one — Railway's convention, which the Railpack builder
assumes, and what makes zero-config builds work (`process.env.PORT || 3000` and
friends). Because the number is never promised to the image, it stays a
platform-side detail that can change without breaking existing builds.

Stated plainly: **an app that hardcodes a port and ignores `$PORT` will only
work if it happens to match `containerPort`.** That is not a contract we
maintain, and such an image can break when the default moves.

The placeholder image is the one exception — it is ours, and nginx will not
read `$PORT` without templating, so it is pinned to the default and must be
rebuilt if the default ever changes.

## The ownership assertion

`custom.imageRef` in
[`chart/templates/_helpers.tpl`](chart/templates/_helpers.tpl) asserts that the
`{user_id}` repository half of `image` equals `caelus.owner.id`, and `fail`s if
not:

```
Error: execution error at (custom/templates/deployment.yaml:24:20): custom: image
repository "7" does not match deployment owner "5"; an image can only be deployed
by the user it was built for
```

The message names both values on purpose — it surfaces to the end user as a
deployment error, and a raw Helm template error would tell them nothing.

Two properties make this sound, and **both must hold**:

1. `caelus.owner.id` is injected by
   `_build_owner_overrides` (`api/app/services/reconcile.py`), and
   `merge_values_scoped` (`api/app/services/template_values.py`) applies system
   overrides **last** — so a tenant cannot shadow it with their own values. There
   is a test pinning this ordering in `api/tests/test_reconcile_service.py`.
2. `placeholderImage` is a system value. It is the one image reference that
   bypasses this check, which is exactly why it must never become
   user-settable — that would hand every tenant an arbitrary-image escape hatch.

The check lives in the chart rather than in `update_deployment` so that no build-
or image-specific special-casing leaks into the generic deployment path shared by
every other product.

## No image yet: the placeholder

`freepod init` creates the deployment — and claims and routes its hostname —
*before* anything has been built. With `image` unset the chart renders and
installs cleanly, running `placeholderImage` rather than scaling to zero, so a
freshly claimed domain serves a real page instead of a Traefik 503.

The placeholder is built from [`placeholder/`](placeholder/): nginx serving one
self-contained landing page (no external CSS, fonts, or images — it has to render
standalone, on a hostname with nothing else behind it).

```bash
cd products/custom/placeholder
docker build -t registry.home/caelus/custom-placeholder:0.1.0 .
docker push registry.home/caelus/custom-placeholder:0.1.0
```

Never re-push an existing tag: bump the version and repoint `placeholderImage`
in `chart/values.yaml` (and the chart version with it), so running deployments
are not swapped out from under themselves by a mutated tag.

## Manual install

```bash
helm lint products/custom/chart
helm template demo products/custom/chart          # placeholder, no ingress

helm upgrade --install demo products/custom/chart \
  --namespace demo --create-namespace \
  --set image=5@sha256:<64 hex chars> \
  --set caelus.owner.id=5 \
  --set caelus.ingress.enabled=true \
  --set caelus.ingress.host=demo.example.com \
  --set caelus.ingress.tls.wildcard=true
```

Both `helm lint` and `helm template` pass standalone with the shipped defaults:
`image` is empty (placeholder) and `caelus.ingress.enabled` is `false`.

## Build and publish

Caelus deploys charts by OCI reference, so the chart must be packaged and pushed
before a product template can point at it. This chart has no dependencies, so
there is no `helm dependency build` step.

```bash
cd products/custom/chart
helm lint .
helm package .                 # -> custom-0.1.0.tgz
helm push custom-0.1.0.tgz oci://registry.home/helm --insecure-skip-tls-verify
```

Optionally verify the push:

```bash
helm pull oci://registry.home/helm/custom --version 0.1.0 \
  --insecure-skip-tls-verify --destination /tmp
```

As with the placeholder image: bump `version` in `Chart.yaml` rather than
re-pushing an existing chart version.

## Caelus product template

| Field | Value |
|---|---|
| Chart ref | `oci://registry.home/helm/custom` |
| Chart version | `0.1.0` |
| Default Helm values | `{}` — the chart's own defaults already carry `registry`, `placeholderImage`, and `containerPort`. Set them here only to override per environment. |
| User values schema | see below |

### User values schema

The `values_schema_json` for the template row. This is a **different, much
smaller** schema than `chart/values.schema.json`: that one validates the fully
merged values Helm-side, this one defines the two fields a tenant may set and
drives the deployment form.

Two values are required:

- `hostname` carries `"title": "hostname"`. `_iter_hostname_paths` /
  `normalize_and_return_hostname` (`api/app/services/deployments.py`) scan the
  schema for that title (case-insensitively) to derive and claim the deployment's
  hostname. Without it, hostname claiming silently does nothing.
- `image` is **not** in `required`. The deployment is created before any build
  exists; requiring it would make `freepod init` impossible.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "hostname": {
      "type": "string",
      "title": "hostname",
      "description": "The domain name your application is served on",
      "minLength": 1,
      "maxLength": 253,
      "pattern": "^((?!-)(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]?\\.)+(xn--)?[a-z0-9-]{2,}$"
    },
    "image": {
      "type": "string",
      "title": "Image",
      "description": "The build to run, as \"{user_id}@{digest}\". Leave empty to serve the placeholder page until your first build is released.",
      "pattern": "^[0-9]+@sha256:[a-f0-9]{64}$"
    }
  },
  "required": [
    "hostname"
  ],
  "additionalProperties": false
}
```
