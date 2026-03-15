## Why

The Admin page is a monolithic collection of loosely arranged widgets for managing products and templates. Creating and inspecting templates requires jumping between disconnected cards, there is no live preview of what the user-facing deploy form will look like, and the layout doesn't communicate the relationship between a product and its template versions. This redesign replaces the current layout with an integrated product configuration panel that makes template management intuitive and gives admins a real-time preview of the deploy experience.

## What Changes

- Replace the current grid of standalone cards below the product list with a single product detail panel that appears when a product card is clicked.
- The detail panel shows the product header (name, description, icon -- editable in-place) followed by a tabbed template viewer.
- Each existing template gets a read-only tab (labeled by DB ID, sorted chronologically, canonical template visually indicated). Read-only tabs show chart ref, chart version, schema and defaults in read-only Monaco editors, plus a "Make canonical" button.
- A "New" tab pinned to the right provides a mutable form for creating new templates. It pre-populates from the newest existing template (or a bare-bones default schema if none exist).
- The "New" tab includes a split view: JSON schema editor on the left with a live validity indicator (green/red), and a live preview of the DeployDialog on the right. Below both is the defaults JSON editor.
- Refactor `DeployDialog` into a shared presentational component so the same dialog UI can be used on the Dashboard (with real deploy logic) and on the Admin page (as an inert preview driven by the schema editor).
- Add a "New product" card at the end of the product list that opens a blank product editor for creating a product and its first template in one flow.
- No template deletion in this iteration (avoids deployment FK complexity).
- New templates auto-become canonical only when the product has no canonical template yet (existing behavior preserved).

## Capabilities

### New Capabilities
- `admin-product-detail`: Integrated product detail panel with editable header and tabbed template viewer, replacing the current standalone card layout.
- `admin-template-tabs`: Tabbed interface for browsing template versions (read-only) and creating new ones, with chronological ordering and canonical indicator.
- `admin-schema-preview`: Live deploy dialog preview driven by the JSON schema editor, with real-time validation indicator and debounced updates.
- `deploy-dialog-shared`: Refactored DeployDialog as a shared presentational component usable in both Dashboard deploy flow and Admin preview mode.

### Modified Capabilities
- `hostname-field-ui`: No requirement changes -- reused as-is within the shared DeployDialog component.

## Impact

- **UI components**: `DeployDialog.tsx` refactored into shared `DeployDialogContent` + thin wrappers. `Admin.tsx` largely rewritten. New components: `ProductDetail`, `TemplateTabs`, `TemplateTabReadOnly`, `TemplateTabNew`, `DeployDialogPreview`, `SchemaEditor`. `ProductList` extended with "New product" card. `NewProduct` integrated into the detail panel flow.
- **No API changes**: All existing endpoints are sufficient. No backend modifications needed.
- **No data model changes**: Product and ProductTemplateVersion models remain unchanged.
- **Dependencies**: Monaco editor (already used), MUI Tabs (already available via MUI).
