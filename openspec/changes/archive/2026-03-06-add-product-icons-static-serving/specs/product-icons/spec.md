## ADDED Requirements

### Requirement: Product read contract SHALL expose icon_url and hide storage-relative path
The system MUST store icon paths internally as `rel_icon_path` and expose product icon references externally as `ProductRead.icon_url` absolute API paths.

#### Scenario: Product created without icon
- **WHEN** a product is created without an icon
- **THEN** product read responses SHALL include `icon_url` with value `null`

#### Scenario: Product with icon
- **WHEN** a product has an icon stored at `rel_icon_path = icons/<sha1>.png`
- **THEN** product read responses SHALL include `icon_url = /api/static/icons/<sha1>.png`

#### Scenario: Storage-relative path not exposed
- **WHEN** a client reads product responses from API endpoints
- **THEN** response payloads SHALL NOT expose `rel_icon_path`

### Requirement: Product create SHALL support atomic multipart create-with-icon
The system MUST support multipart `POST /api/products` with product JSON and icon binary as separate form fields so product + icon can be created in one request.

#### Scenario: Multipart create with icon succeeds
- **WHEN** a client submits `POST /api/products` multipart form containing valid product JSON part and valid icon file part
- **THEN** the API SHALL create the product and icon atomically and return product data with non-null `icon_url`

#### Scenario: Multipart create icon processing fails
- **WHEN** multipart `POST /api/products` contains invalid or non-processable icon data
- **THEN** the API SHALL fail the request and SHALL NOT persist a product record

#### Scenario: ProductCreate model remains icon-free
- **WHEN** product create JSON schema/model is validated
- **THEN** icon input SHALL be handled only via multipart file field and not as a `ProductCreate` attribute

### Requirement: Product icon upload endpoint SHALL process and persist canonical PNG icons
The system MUST provide `PUT /api/products/{product_id}/icon` for binary image uploads and persist a canonical icon file.

#### Scenario: Successful icon upload
- **WHEN** a valid image file is uploaded to `PUT /api/products/{product_id}/icon`
- **THEN** the system SHALL decode the image, normalize orientation, center-crop to a square, downscale to at most `256x256` without upscaling, encode as PNG, store it under `STATIC_PATH/icons/<sha1>.png`, update `product.rel_icon_path`, and expose updated `icon_url`

#### Scenario: Unknown product
- **WHEN** an icon upload is requested for a product id that does not exist
- **THEN** the API SHALL return `404`

### Requirement: Product icon files SHALL be immutable
The system MUST treat uploaded product icon files as immutable assets.

#### Scenario: Replacing an existing icon
- **WHEN** a new icon is uploaded for a product that already has an icon
- **THEN** the system SHALL write a content-hash filename based on processed PNG bytes, update `rel_icon_path` to the resulting path, and SHALL NOT delete existing files

#### Scenario: Product deletion
- **WHEN** a product is deleted
- **THEN** previously uploaded icon files SHALL remain on the filesystem

### Requirement: Icon upload endpoint SHALL enforce lightweight input limits
The system MUST reject oversized icon inputs using simple server-side checks.

#### Scenario: File exceeds size cap
- **WHEN** uploaded icon payload size exceeds `10MB`
- **THEN** the API SHALL reject the request with a client error and SHALL NOT persist icon data or update `rel_icon_path`

#### Scenario: Image exceeds resolution cap
- **WHEN** decoded image dimensions exceed `2048x2048`
- **THEN** the API SHALL reject the request with a client error and SHALL NOT persist icon data or update `rel_icon_path`

### Requirement: Product icon read endpoint SHALL redirect to static path
The system MUST provide `GET /api/products/{product_id}/icon` as a product-scoped icon lookup.

#### Scenario: Product has icon
- **WHEN** `GET /api/products/{product_id}/icon` is requested and `rel_icon_path` is set
- **THEN** the API SHALL return `302` with `Location: /api/static/{rel_icon_path}`

#### Scenario: Product has no icon
- **WHEN** `GET /api/products/{product_id}/icon` is requested and `rel_icon_path` is null
- **THEN** the API SHALL return `404`

### Requirement: CLI and Admin create-product flows SHALL support icon input without two-step API create
The system MUST support icon-aware create-product UX in CLI and Admin flows using the multipart create contract.

#### Scenario: CLI create-product with icon
- **WHEN** `create-product --icon <path>` is invoked with valid inputs
- **THEN** the command SHALL create the product with icon in one logical operation and return product output with non-null `icon_url`

#### Scenario: Admin form preview and submit
- **WHEN** an admin selects an icon file in the New Product widget
- **THEN** the UI SHALL show a local preview before submission using the dedicated icon input component

#### Scenario: Admin create submits multipart payload
- **WHEN** an admin submits create-product with icon from the New Product widget
- **THEN** the UI SHALL send multipart product+icon create input to `POST /api/products` rather than create-then-upload sequencing
