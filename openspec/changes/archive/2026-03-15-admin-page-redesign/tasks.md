## 1. Refactor DeployDialog

- [x] 1.1 Extract `DeployDialogContent` component from `DeployDialog` with props: product, valuesSchemaJson, defaultValuesJson, onLaunch (optional), onCancel (optional), disabled
- [x] 1.2 Refactor `DeployDialog` to wrap `DeployDialogContent` in a MUI Dialog, keeping all existing fetch/mutation logic
- [x] 1.3 Verify Dashboard deploy flow works identically after refactor

## 2. ProductDetail container

- [x] 2.1 Create `ProductDetail` component that renders the `SelectedProduct` header and a placeholder for template tabs
- [x] 2.2 Wire `ProductDetail` into `Admin.tsx` below the product list, replacing the current grid layout
- [x] 2.3 Show `ProductDetail` only when a product is selected

## 3. TemplateTabs

- [x] 3.1 Create `TemplateTabs` component with MUI scrollable Tabs, one tab per template sorted by `created_at` ascending, labeled by DB ID
- [x] 3.2 Add canonical template visual indicator (star icon or similar) on the canonical tab
- [x] 3.3 Add "New" tab pinned to the right end of the tab bar
- [x] 3.4 Wire `TemplateTabs` into `ProductDetail` below the product header

## 4. TemplateTabReadOnly

- [x] 4.1 Create `TemplateTabReadOnly` component showing chart ref, chart version, and read-only Monaco editors for schema and defaults
- [x] 4.2 Add "Make canonical" button that updates `product.template_id`, disabled when template is already canonical
- [x] 4.3 Wire `TemplateTabReadOnly` as the tab panel content for existing template tabs

## 5. TemplateTabNew

- [x] 5.1 Create `TemplateTabNew` component with editable chart ref and chart version fields
- [x] 5.2 Add Monaco schema editor with live JSON validation indicator (green tick / red exclamation)
- [x] 5.3 Add `DeployDialogContent` preview alongside the schema editor, fed by the last valid schema, with debounced updates
- [x] 5.4 Add Monaco defaults editor below the schema editor and preview
- [x] 5.5 Add Save/Add button, disabled when schema or defaults JSON is invalid or required fields are empty
- [x] 5.6 Pre-populate form fields from newest existing template, or `DEFAULT_VALUES_SCHEMA` if no templates exist
- [x] 5.7 Wire template creation mutation: create template, auto-set canonical if none exists, invalidate queries

## 6. New product card

- [x] 6.1 Add a "New product" card as the last item in `ProductList`
- [x] 6.2 Wire "New product" card to show `NewProduct` form in the detail area, switching to the new product's `ProductDetail` on success
- [x] 6.3 Handle product creation flow: create product, invalidate queries, auto-select the new product

## 7. Wire together and clean up

- [x] 7.1 Remove old Admin.tsx grid layout, standalone template cards, and inline components that are now replaced
- [x] 7.2 Move any remaining inline logic from Admin.tsx into appropriate components
- [x] 7.3 Verify all mutations (create product, create template, update canonical, update product name/description/icon) work correctly in the new layout
