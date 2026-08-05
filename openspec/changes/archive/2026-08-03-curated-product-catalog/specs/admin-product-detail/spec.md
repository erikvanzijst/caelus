## MODIFIED Requirements

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
