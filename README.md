# Caelus

Cloud provisioning tool with FastAPI + SQLModel + Alembic and a Typer CLI.

## Local dev
- Set `DATABASE_URL` (defaults to sqlite `./caelus.db`).
- Run API: `uvicorn app.main:app --reload`
- Run CLI (uv-managed venv): `uv run python -m app.cli --help`

## Devcontainer
A [devcontainer](https://containers.dev/) is provided for sandboxed development:
- Create the devcontainer: `./dev build`
- Start the devcontainer in the background: `./dev up`
- Open a shell in the devcontainer: `./dev sh`
- Run a command in the devcontainer: `./dev run uv run pytest -s`
- Shut down the devcontainer: `./dev down`

## API Endpoints

### /products
- `POST /products` – Create a new product.
- `GET /products` – List all products.
- `GET /products/{product_id}` – Retrieve a product.
- `UPDATE /products/{product_id}` – Modify a product.
- `DELETE /products/{product_id}` – Delete a product.
- `POST /products/{product_id}/templates` – Create a template version for a product.
- `GET /products/{product_id}/templates` – List template versions for a product.
- `GET /products/{product_id}/templates/{template_id}` – Get a specific template version.
- `DELETE /products/{product_id}/templates/{template_id}` – Delete a template version.

### /users
- `POST /users` – Create a new user.
- `GET /users` – List all users.
- `GET /users/{user_id}` – Retrieve a user.
- `DELETE /users/{user_id}` – Delete a user.
- `POST /users/{user_id}/deployments` – Create a deployment for a user.
- `GET /users/{user_id}/deployments` – List deployments for a user.
- `GET /users/{user_id}/deployments/{deployment_id}` – Get a specific deployment.
- `DELETE /users/{user_id}/deployments/{deployment_id}` – Delete a deployment.

## CLI ↔ REST parity
The Typer CLI (`python -m app.cli …`) mirrors the functionality of the REST API. Any operation available via an HTTP endpoint can be performed with the equivalent CLI command, and vice‑versa. This ensures both interfaces stay in lockstep.