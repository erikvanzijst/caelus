## ADDED Requirements

### Requirement: Monaco excluded from the initial bundle
The Monaco editor library SHALL be code-split into a separate chunk that is
excluded from the application's initial JavaScript bundle, and the browser
SHALL load that chunk only when an editor is first rendered. This applies to
`@monaco-editor/react` and the underlying `monaco-editor` package.

#### Scenario: Initial load on a non-admin page
- **WHEN** a visitor loads the landing page, the dashboard, or a legal page
- **THEN** the initial bundle downloaded by the browser SHALL NOT contain the
  Monaco editor code, and no Monaco chunk SHALL be requested

#### Scenario: Production build output
- **WHEN** the UI is built for production
- **THEN** Monaco SHALL appear in a separate async chunk distinct from the
  initial entry bundle, and the initial bundle size SHALL be smaller than a
  build that includes Monaco eagerly

### Requirement: Monaco loaded on demand for admin template editors
The application SHALL dynamically import Monaco and render the editor once the
chunk has loaded whenever an admin views a screen that renders a Monaco editor
(a read-only template tab or the "New" template tab).

#### Scenario: Opening a read-only template tab
- **WHEN** an admin opens an existing template tab that displays read-only
  schema and default-values editors
- **THEN** the application SHALL load the Monaco chunk on demand and render the
  read-only editors with the template's contents once loaded

#### Scenario: Opening the New template tab
- **WHEN** an admin opens the "New" template tab
- **THEN** the application SHALL load the Monaco chunk on demand and render the
  editable schema and system-values editors once loaded

#### Scenario: Subsequent editors reuse the loaded chunk
- **WHEN** the Monaco chunk has already been loaded during the session
- **THEN** further editors SHALL render without issuing an additional network
  request for the Monaco chunk

### Requirement: Loading fallback while Monaco loads
While the Monaco chunk is being fetched, the application SHALL display a
non-blocking loading fallback in place of the editor so the surrounding UI
remains usable and the layout does not collapse.

#### Scenario: Fallback shown during fetch
- **WHEN** an editor mounts and the Monaco chunk has not yet finished loading
- **THEN** a loading indicator SHALL be shown where the editor will appear

#### Scenario: Fallback replaced by editor
- **WHEN** the Monaco chunk finishes loading
- **THEN** the loading indicator SHALL be replaced by the functioning editor

### Requirement: Existing editor behaviour preserved
Lazy loading SHALL NOT change any existing editor-backed behaviour. Read-only
editors SHALL remain read-only, editable editors SHALL remain editable, JSON
validation indicators SHALL continue to reflect editor contents, and the
make-canonical and add-template actions SHALL continue to function.

#### Scenario: Read-only editor stays read-only
- **WHEN** a template's schema and default-values editors are rendered in a
  read-only tab after lazy loading
- **THEN** the editors SHALL be read-only and SHALL display the template's
  stored values

#### Scenario: Editable schema validation still works
- **WHEN** an admin edits the schema in the "New" tab so it becomes invalid
  JSON after Monaco has loaded
- **THEN** the validation indicator SHALL show the invalid state and the "Add
  template" action SHALL be disabled, exactly as before

#### Scenario: Add template still submits parsed values
- **WHEN** an admin fills in a valid chart reference, chart version, and schema
  in the lazily-loaded "New" tab and clicks "Add template"
- **THEN** the save action SHALL be invoked with the parsed values just as it
  was before lazy loading

### Requirement: Tests await lazily-rendered editors
Automated tests that render the Monaco-bearing components SHALL account for the
asynchronous nature of the lazily-loaded editor, awaiting the editor's
appearance (for example via `findBy*` queries or explicit `await`) rather than
querying for it synchronously, and the test environment SHALL resolve the
dynamic import of the editor.

#### Scenario: Test renders a lazy editor
- **WHEN** a test renders a component that lazily loads a Monaco editor
- **THEN** the test SHALL await the editor's appearance before asserting on it,
  and the dynamic import SHALL resolve in the test environment without error
