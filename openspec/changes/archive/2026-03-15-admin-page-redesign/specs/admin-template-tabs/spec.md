## ADDED Requirements

### Requirement: Tabbed template viewer
The product detail panel SHALL display a tab component below the product header with one tab per template version associated with the product. Tabs SHALL be ordered chronologically with the oldest template on the left and the newest on the right.

#### Scenario: Multiple templates
- **WHEN** a product has three template versions created at T1, T2, T3
- **THEN** tabs SHALL appear in order T1 (left), T2 (middle), T3 (right)

#### Scenario: Scrollable tabs
- **WHEN** a product has more templates than can fit in the visible tab bar
- **THEN** the tab bar SHALL be scrollable with scroll buttons

### Requirement: Tab labels and canonical indicator
Each template tab SHALL be labeled with the template's database ID. The tab for the canonical template (the one matching `product.template_id`) SHALL display an additional visual indicator distinguishing it from non-canonical tabs.

#### Scenario: Canonical template tab
- **WHEN** a product has `template_id` set to template 42
- **THEN** the tab for template 42 SHALL display a visual indicator (e.g., star icon) alongside its label

#### Scenario: Non-canonical template tab
- **WHEN** a template is not the canonical template
- **THEN** its tab SHALL display only the DB ID as its label

### Requirement: New tab pinned to right
A "New" tab SHALL always appear as the rightmost tab, after all existing template tabs. This tab provides the form for creating a new template version.

#### Scenario: New tab position
- **WHEN** a product has templates with IDs 10, 11, 12
- **THEN** the tabs SHALL appear as: 10, 11, 12, New

### Requirement: Read-only template tab content
Each existing template tab SHALL display the template's chart reference, chart version, user values JSON schema, and default values JSON in a read-only view. The JSON fields SHALL be displayed in read-only Monaco editors.

#### Scenario: Viewing an existing template
- **WHEN** an admin clicks on an existing template tab
- **THEN** the pane SHALL show the chart ref, chart version, and read-only Monaco editors for the schema and defaults

### Requirement: Make canonical button
Each read-only template tab SHALL include a "Make canonical" button that sets that template as the product's canonical template. The button SHALL be disabled or hidden if the template is already canonical.

#### Scenario: Making a template canonical
- **WHEN** an admin clicks "Make canonical" on a non-canonical template tab
- **THEN** the product's `template_id` SHALL be updated to that template's ID and the canonical indicator SHALL move to that tab

#### Scenario: Already canonical
- **WHEN** a template is already the canonical template
- **THEN** the "Make canonical" button SHALL be disabled or not shown
