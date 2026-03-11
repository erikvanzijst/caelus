## ADDED Requirements

### Requirement: Product read endpoints are open to all authenticated users
`GET /api/products`, `GET /api/products/{product_id}`, `GET /api/products/{product_id}/templates`, `GET /api/products/{product_id}/templates/{template_id}`, and `GET /api/products/{product_id}/icon` SHALL remain accessible to any authenticated user.

#### Scenario: Non-admin lists products
- **WHEN** a non-admin user sends GET /api/products
- **THEN** the endpoint returns the list of products with HTTP 200

#### Scenario: Non-admin views product details
- **WHEN** a non-admin user sends GET /api/products/{product_id}
- **THEN** the endpoint returns the product with HTTP 200

#### Scenario: Non-admin lists templates
- **WHEN** a non-admin user sends GET /api/products/{product_id}/templates
- **THEN** the endpoint returns the templates with HTTP 200

#### Scenario: Non-admin views template details
- **WHEN** a non-admin user sends GET /api/products/{product_id}/templates/{template_id}
- **THEN** the endpoint returns the template with HTTP 200

#### Scenario: Non-admin views product icon
- **WHEN** a non-admin user sends GET /api/products/{product_id}/icon
- **THEN** the endpoint returns the icon redirect with HTTP 302

### Requirement: Product creation is admin-only
`POST /api/products` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin creates product
- **WHEN** an admin user sends POST /api/products with a valid payload
- **THEN** the endpoint creates the product and returns HTTP 201

#### Scenario: Non-admin creates product
- **WHEN** a non-admin user sends POST /api/products with a valid payload
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Product update is admin-only
`PUT /api/products/{product_id}` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin updates product
- **WHEN** an admin user sends PUT /api/products/{product_id} with a valid payload
- **THEN** the endpoint updates the product and returns HTTP 200

#### Scenario: Non-admin updates product
- **WHEN** a non-admin user sends PUT /api/products/{product_id} with a valid payload
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Product deletion is admin-only
`DELETE /api/products/{product_id}` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin deletes product
- **WHEN** an admin user sends DELETE /api/products/{product_id}
- **THEN** the endpoint deletes the product and returns HTTP 204

#### Scenario: Non-admin deletes product
- **WHEN** a non-admin user sends DELETE /api/products/{product_id}
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Template creation is admin-only
`POST /api/products/{product_id}/templates` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin creates template
- **WHEN** an admin user sends POST /api/products/{product_id}/templates with a valid payload
- **THEN** the endpoint creates the template and returns HTTP 201

#### Scenario: Non-admin creates template
- **WHEN** a non-admin user sends POST /api/products/{product_id}/templates with a valid payload
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Template deletion is admin-only
`DELETE /api/products/{product_id}/templates/{template_id}` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin deletes template
- **WHEN** an admin user sends DELETE /api/products/{product_id}/templates/{template_id}
- **THEN** the endpoint deletes the template and returns HTTP 204

#### Scenario: Non-admin deletes template
- **WHEN** a non-admin user sends DELETE /api/products/{product_id}/templates/{template_id}
- **THEN** the endpoint returns HTTP 403 Forbidden

### Requirement: Product icon upload is admin-only
`PUT /api/products/{product_id}/icon` SHALL require admin authorization. Non-admin users SHALL receive HTTP 403 Forbidden.

#### Scenario: Admin uploads icon
- **WHEN** an admin user sends PUT /api/products/{product_id}/icon with a file
- **THEN** the endpoint processes the icon and returns HTTP 200

#### Scenario: Non-admin uploads icon
- **WHEN** a non-admin user sends PUT /api/products/{product_id}/icon with a file
- **THEN** the endpoint returns HTTP 403 Forbidden
