# Caelus

Cloud provisioning tool with FastAPI + SQLModel + Alembic + Typer CLI and React UI.


## Repo layout

This a monorepo with two packages:
- [api/](./api/README.md): the FastAPI app
- [ui/](./ui/README.md): the React app


## Devcontainer
A [devcontainer](https://containers.dev/) is provided for sandboxed development:
- Create the devcontainer: `./dev build`
- Start the devcontainer in the background: `./dev up`
- Open a shell in the devcontainer: `./dev sh`
- Run a command in the devcontainer: `./dev run uv run pytest -s`
- Shut down the devcontainer: `./dev down`
