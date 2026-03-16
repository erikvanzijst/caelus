## ADDED Requirements

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
The detail panel SHALL display the product's name, description, and icon in a header layout matching the deployment cards on the Dashboard (icon on the right). Name and description SHALL be editable in-place. The icon SHALL be changeable by clicking it.

#### Scenario: Editing product name
- **WHEN** an admin clicks the product name in the detail header
- **THEN** the name SHALL become an editable text field that saves on blur or Enter

#### Scenario: Changing product icon
- **WHEN** an admin clicks the product icon in the detail header
- **THEN** a file picker SHALL open allowing the admin to upload a new icon image

### Requirement: New product card in product list
The product list SHALL display a "New product" card as the last item in the list. Clicking it SHALL show the detail panel in creation mode with empty name, description, and icon fields, and only a "New" template tab.

#### Scenario: Creating a new product
- **WHEN** an admin clicks the "New product" card
- **THEN** the detail panel SHALL appear with empty editable fields for name, description, and icon

#### Scenario: New product template flow
- **WHEN** an admin is creating a new product
- **THEN** the template area SHALL show only the "New" tab for creating the first template
