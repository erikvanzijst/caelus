# Caelus

Cloud provisioning tool with FastAPI + SQLModel + Alembic + Typer CLI and React UI.


## Repo layout

This a monorepo with three packages:
- [api/](./api/README.md) -- the FastAPI app
- [ui/](./ui/README.md) -- the React app
- [k8s/](./k8s/README.md) -- backend kubernetes connectivity utilities


## Devcontainer
A [devcontainer](https://containers.dev/) is provided for sandboxed development:
- Create the devcontainer: `./dev build`
- Start the devcontainer in the background: `./dev up`
- Open a shell in the devcontainer: `./dev sh`
- Run a command in the devcontainer: `./dev run uv run pytest -s`
- Shut down the devcontainer: `./dev down`

## Kubernetes
Caelus is built to provision application instances into a Kubernetes backend.

The `k8s/` directory contains provisioning utilities and setup instructions for connecting local development workflows to Kubernetes (including generated kubeconfig files).

When using `kubectl` or any other Kubernetes client, always pass the kubeconfig explicitly:
- `--kubeconfig ./k8s/kubeconfigs/<config.yaml>`
