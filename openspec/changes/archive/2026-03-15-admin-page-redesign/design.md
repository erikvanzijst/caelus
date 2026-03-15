## Context

The Admin page (`ui/src/pages/Admin.tsx`, ~520 lines) is a monolithic component containing inline sub-components (`NewProduct`, `SelectedProduct`, `ProductList`) and direct template CRUD logic. The current layout uses a two-column grid: product management on the left, template management on the right. There is no visual connection between a product and its templates, no preview of what the deploy form will look like for a given schema, and no chronological view of template versions.

The data model is stable and sufficient: `Product` has a `template_id` FK pointing to its canonical `ProductTemplateVersion`. Templates are immutable once created (no update endpoint). The existing API endpoints cover all needed operations.

`DeployDialog` currently fetches templates internally via React Query, constructs the canonical template lookup, and handles deployment creation. It cannot be reused as a preview because it is tightly coupled to the deploy flow.

## Goals / Non-Goals

**Goals:**
- Replace the Admin page layout below the product list with an integrated product detail panel.
- Provide a tabbed chronological view of all template versions per product.
- Give admins a live preview of the deploy dialog while editing a new template's JSON schema.
- Refactor DeployDialog into a shared presentational core usable in both deploy and preview contexts.
- Decompose the monolithic Admin page into focused, single-responsibility components.

**Non-Goals:**
- Template deletion (deferred due to deployment FK complexity).
- Template editing/updating (templates are immutable by design).
- Backend API changes (current endpoints are sufficient).
- Changing the product list appearance (only adding the "New product" card).

## Decisions

### 1. DeployDialog refactoring strategy

**Decision**: Extract a `DeployDialogContent` component that receives all data as props (product, schema, defaults, button handlers). Create two thin consumers:
- `DeployDialog` (Dashboard): wraps `DeployDialogContent` in a MUI `Dialog`, fetches templates via React Query, provides deploy mutation handlers.
- Admin preview: renders `DeployDialogContent` directly (not in a Dialog) inside the template tab, passing the live schema from the editor.

**Why not a `preview` prop on the existing DeployDialog**: A boolean mode flag would create branching logic throughout the component (skip fetching, skip userId, disable buttons conditionally). Two thin wrappers around a shared core is cleaner and follows composition over configuration.

**Why not render in a Dialog on the Admin page**: The preview needs to sit inline within the template tab layout (side-by-side with the schema editor), not as a modal overlay. Extracting the content makes this natural.

### 2. Component decomposition

**Decision**: Create these new components in `ui/src/components/`:

| Component | Responsibility |
|---|---|
| `DeployDialogContent` | Shared presentational core: product header, UserValuesForm, action buttons. Props-driven. |
| `ProductDetail` | Container for selected product: renders header (SelectedProduct) + TemplateTabs. |
| `TemplateTabs` | MUI `Tabs` (scrollable) with one tab per template + "New" tab. Manages active tab state. |
| `TemplateTabReadOnly` | Read-only pane: chart ref/version, schema + defaults in Monaco (readOnly), "Make canonical" button. |
| `TemplateTabNew` | Mutable pane: chart ref/version fields, schema editor with validity indicator, DeployDialogContent preview, defaults editor. Save button. |

**Why not keep logic in Admin.tsx**: The current page is ~520 lines with inline components. The redesign adds significant new functionality (tabs, live preview, validation). Keeping it monolithic would make it unmaintainable.

### 3. Schema editor validation and preview sync

**Decision**: The `TemplateTabNew` component holds `schemaText` (raw string from Monaco) and `validSchema` (last successfully parsed JSON object) as separate state values. On every Monaco change:
1. Try `JSON.parse(schemaText)`.
2. If valid: update `validSchema`, show green indicator.
3. If invalid: keep `validSchema` unchanged, show red indicator.

The preview always receives `validSchema`. Debouncing is applied to the parse attempt (300ms) to avoid thrashing during typing.

**Why separate state for text vs parsed**: Monaco needs the raw string (including invalid intermediate states). The preview needs valid JSON. Keeping them separate avoids either component receiving inappropriate data.

### 4. "New product" flow

**Decision**: Add a synthetic card to `ProductList` that appears last. Clicking it sets a `creatingNewProduct` state in Admin.tsx which renders `ProductDetail` in creation mode. In this mode, the product header fields (name, description, icon) are empty and editable. The template area shows only the "New" tab. Saving creates the product first, then the template.

**Why not a separate dialog**: Keeping the creation flow in the same detail panel layout means the admin learns one interface for both creating and editing products. It also naturally supports creating the first template as part of the product creation flow.

### 5. Tab ordering and labeling

**Decision**: Tabs are sorted by `template.created_at` ascending (oldest first, newest last). Tab labels show the template's DB `id`. The canonical template's tab gets a small star icon or chip indicator. The "New" tab is pinned to the right end.

**Why DB ID as label**: Template versions don't have a user-facing version label that's always set (the `version_label` field is optional and rarely used). The DB ID is always unique, always present, and matches what admins see in API responses and logs.

### 6. "New" tab pre-population

**Decision**: When the "New" tab is selected, its form fields are pre-populated from the newest existing template (last in the sorted list): `chart_ref`, `chart_version`, `values_schema_json`, `default_values_json`. If no templates exist, `values_schema_json` defaults to `DEFAULT_VALUES_SCHEMA` (the existing constant in Admin.tsx) and other fields start empty.

**Why copy from newest**: The newest template is most likely to be the closest starting point for the next version. Admins typically iterate on chart versions while keeping the schema stable.

## Risks / Trade-offs

- **Monaco editor bundle size**: Already in use on the Admin page, so no new dependency cost.
- **Live preview performance**: Parsing JSON and re-rendering the UserValuesForm on every keystroke could be expensive. Mitigation: 300ms debounce on schema parsing, and only updating the preview when the parsed result actually changes (reference equality check).
- **Product creation flow complexity**: Creating a product and its first template in one flow requires a two-step save (create product, then create template). Mitigation: clear UI feedback for each step, disable the template save until the product is created.
- **Tab overflow with many templates**: Products with many versions could create many tabs. Mitigation: MUI Tabs `variant="scrollable"` with scroll buttons handles this natively.
