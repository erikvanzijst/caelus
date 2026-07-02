## 1. Lazy-loading wrapper

- [x] 1.1 Create `ui/src/components/LazyMonaco.tsx` that lazily imports
  `@monaco-editor/react` via `React.lazy(() => import('@monaco-editor/react'))`
  and renders it inside a `<Suspense>` boundary.
- [x] 1.2 Add a lightweight loading fallback (e.g. an MUI skeleton or "Loading
  editor…" placeholder) sized to fill the editor container so the layout does
  not shift while the chunk loads.
- [x] 1.3 Forward all editor props (`height`, `defaultLanguage`, `value`,
  `onChange`, `options`, `theme`) through the wrapper unchanged.

## 2. Adopt the wrapper in admin template tabs

- [x] 2.1 Replace the direct `import Editor from '@monaco-editor/react'` in
  `ui/src/components/TemplateTabReadOnly.tsx` with the `LazyMonaco` wrapper.
- [x] 2.2 Replace the direct `import Editor from '@monaco-editor/react'` in
  `ui/src/components/TemplateTabNew.tsx` with the `LazyMonaco` wrapper.
- [x] 2.3 Verify no other module statically imports `@monaco-editor/react`
  (grep the `ui/src` tree) so nothing pulls Monaco back into the initial graph.

## 3. Optional admin route-level splitting

- [x] 3.1 (Optional) Lazy-load the admin pages/panels in `ui/src/App.tsx`
  (and/or `ui/src/pages/Admin.tsx`) with `React.lazy` + `Suspense` to defer the
  rest of the admin surface from the initial bundle.

## 4. Tests

- [x] 4.1 Update `ui/src/components/TemplateTabNew.test.tsx` to await the
  lazily-rendered editor (convert editor lookups to `findBy*`/`await`), keeping
  the existing `@monaco-editor/react` mock.
- [x] 4.2 Update `ui/src/components/TemplateTabs.test.tsx` the same way so the
  read-only and new tabs resolve their lazy editors before assertions.
- [x] 4.3 Confirm the test environment resolves the dynamic import without
  error and that the mock specifier matches the lazily-imported module.
- [x] 4.4 Run `npm test` (Vitest) and confirm the suite passes.

## 5. Verify bundle and behaviour

- [x] 5.1 Run `npm run build` and confirm Monaco is emitted as a separate async
  chunk that is not part of the initial entry bundle, and that the initial
  bundle is smaller than before.
- [x] 5.2 Manually verify in the admin template tabs that read-only editors
  stay read-only, the "New" tab editors are editable, JSON validation
  indicators still work, the loading fallback appears on first load, and the
  make-canonical / add-template actions still function.
