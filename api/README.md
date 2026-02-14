# API

## Local dev
- Run API: `uvicorn app.main:app --host 0.0.0.0 --reload`
- Run CLI (uv-managed venv): `uv run python -m app.cli --help`


## Database migrations
- To create a new migration: `uv run alembic revision --autogenerate -m <name>`
- Run migrations: `uv run alembic upgrade head`


## API Endpoints

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

The Typer CLI (`python -m app.cli …`) mirrors the functionality of the REST
API. Any operation available via an HTTP endpoint can be performed with the
equivalent CLI command, and vice‑versa. This ensures both interfaces stay in
lockstep.

## V1 Reconciliation Constraints

1. Templates are Helm-only (`package_type=helm-chart`).
2. Database is the source of truth for desired deployment state.
3. Reconciliation queue is DB-backed (Postgres path uses `FOR UPDATE SKIP LOCKED`).
4. User-editable template values are scoped under `values.user.*`.
5. Admin-only upgrade policy is enforced via `user.is_admin`.
6. Deployment identity naming contract:
   - `deployment_uid = {product_slug}-{user_slug}-{suffix6}`
   - DNS label-safe (`[a-z0-9-]`, max 63 chars)
   - `namespace_name = deployment_uid`
   - `release_name = deployment_uid`
