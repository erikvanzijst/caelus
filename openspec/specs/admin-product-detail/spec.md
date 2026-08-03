# admin-product-detail Specification

## Purpose

Defines the admin product detail panel: how it opens from the product list, how
the product header is presented and edited in place, and how it renders
read-only for catalog-managed (curated) products.

## Requirements

### Requirement: Product detail panel appears on product selection
When an admin clicks a product card in the product list, a detail panel SHALL appear below the product list showing the full configuration of that product. Clicking a different product SHALL switch the detail panel to that product. The detail panel SHALL not appear when no product is selected.

#### Scenario: Selecting a product
- **WHEN** an admin clicks a product card in the product list
- **THEN** a detail panel SHALL appear below the product list showing that product's configuration

#### Scenario: Switching products
- **WHEN** an admin clicks a different product card while a detail panel is open
- **THEN** the detail panel SHALL update to show the newly selected product's configuration

#### Scenario: No product selected
- **WHEN** no product is selected
- **THEN** no detail panel SHALL be displayed below the product list

### Requirement: Product header with inline editing
The detail panel SHALL display the product's name, description, and icon in a header layout matching the deployment cards on the Dashboard (icon on the right). For non-curated products, name and description SHALL be editable in-place and the icon SHALL be changeable by clicking it. For curated products, the header SHALL be read-only and SHALL indicate that the product is managed by the catalog, naming the catalog file to edit instead.

#### Scenario: Editing product name
- **WHEN** an admin clicks the product name in the detail header of a non-curated product
- **THEN** the name SHALL become an editable text field that saves on blur or Enter

#### Scenario: Changing product icon
- **WHEN** an admin clicks the product icon in the detail header of a non-curated product
- **THEN** a file picker SHALL open allowing the admin to upload a new icon image

#### Scenario: Curated product header is read-only
- **WHEN** an admin views the detail header of a curated product
- **THEN** the name, description, and icon SHALL NOT be editable
- **AND** the panel SHALL indicate the product is catalog-managed and name its catalog file

### Requirement: New product card in product list
The product list SHALL display a "New product" card as the last item in the list. Clicking it SHALL show the detail panel in creation mode with empty name, description, and icon fields, and only a "New" template tab.

#### Scenario: Creating a new product
- **WHEN** an admin clicks the "New product" card
- **THEN** the detail panel SHALL appear with empty editable fields for name, description, and icon

#### Scenario: New product template flow
- **WHEN** an admin is creating a new product
- **THEN** the template area SHALL show only the "New" tab for creating the first template
