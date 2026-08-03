## MODIFIED Requirements

### Requirement: New tab pinned to right
A "New" tab SHALL always appear as the rightmost tab, after all existing template tabs, for non-curated products. This tab provides the form for creating a new template version. For curated products the "New" tab SHALL NOT be shown, because template creation is performed by editing the product's catalog file.

#### Scenario: New tab position
- **WHEN** a non-curated product has templates with IDs 10, 11, 12
- **THEN** the tabs SHALL appear as: 10, 11, 12, New

#### Scenario: Curated product has no New tab
- **WHEN** an admin views a curated product with templates 10, 11, 12
- **THEN** the tabs SHALL appear as: 10, 11, 12 with no "New" tab

### Requirement: Make canonical button
Each read-only template tab of a non-curated product SHALL include a "Make canonical" button that sets that template as the product's canonical template. The button SHALL be disabled or hidden if the template is already canonical. For curated products the button SHALL NOT be offered, because the canonical template is determined by the product's catalog file.

#### Scenario: Making a template canonical
- **WHEN** an admin clicks "Make canonical" on a non-canonical template tab of a non-curated product
- **THEN** the product's `template_id` SHALL be updated to that template's ID and the canonical indicator SHALL move to that tab

#### Scenario: Already canonical
- **WHEN** a template is already the canonical template
- **THEN** the "Make canonical" button SHALL be disabled or not shown

#### Scenario: Curated product cannot be repointed from the UI
- **WHEN** an admin views a non-canonical template tab of a curated product
- **THEN** the "Make canonical" button SHALL NOT be offered
- **AND** the tab SHALL indicate that the canonical template is set by the catalog
