## Why

The production UI bundle is roughly 1.5 MB (about 470 KB gzipped), and
`@monaco-editor/react` (Monaco) is the single largest contributor. Monaco is
only needed on the admin template-editing screens, yet it currently ships in
the initial bundle that every visitor downloads — including anonymous visitors
on the landing page, signed-in users on the dashboard, and readers of the
public legal pages. Deferring Monaco until it is actually needed materially
shrinks the initial download for the common case.

## What Changes

- Code-split `@monaco-editor/react` out of the initial bundle so it is fetched
  on demand only when an admin opens a template tab that renders an editor.
- Wrap the Monaco-bearing components (`TemplateTabReadOnly` and
  `TemplateTabNew`) so the editor is loaded via a dynamic `import()` (e.g.
  `React.lazy` + `Suspense`), with a lightweight loading fallback shown while
  the editor chunk downloads.
- Optionally lazy-load the admin route/pages so the entire admin surface
  (which is the only consumer of Monaco) is split from the initial bundle.
- Preserve all existing editor behaviour: read-only template viewing, the
  editable "New" template form, JSON validation indicators, the deploy-dialog
  preview, and the make-canonical / add-template actions.
- Update the affected tests so lazily-rendered editors are awaited
  (`findBy*` / `await`) and the test environment resolves the dynamic import.

No application behaviour visible to users changes other than a brief, explicit
loading state the first time an editor mounts.

## Capabilities

### New Capabilities
- `monaco-lazy-loading`: Defines that the Monaco editor is excluded from the
  initial JS bundle and loaded on demand with a loading fallback, while all
  existing editor-backed admin behaviours remain intact.

### Modified Capabilities
<!-- None. Existing admin-template-tabs and admin-schema-preview requirements
     (that Monaco editors are present and behave a given way) are unchanged;
     only the loading strategy is added, captured here as a new capability. -->

## Impact

- Affected code (UI only, under `ui/`):
  - `ui/src/components/TemplateTabReadOnly.tsx` and
    `ui/src/components/TemplateTabNew.tsx` (Monaco import becomes lazy).
  - Likely a small shared wrapper component for the lazily-loaded editor.
  - Possibly `ui/src/App.tsx` and `ui/src/pages/Admin.tsx` for route-level
    lazy loading of the admin area.
  - Tests: `ui/src/components/TemplateTabNew.test.tsx` and
    `ui/src/components/TemplateTabs.test.tsx` (await lazy editors); test setup
    may need to support the dynamic import.
- Dependencies: no new dependencies; `@monaco-editor/react` stays but is moved
  into a separately-loaded chunk.
- Build output: initial bundle size drops; a new async chunk contains Monaco.
- No API, backend, or infrastructure changes.
