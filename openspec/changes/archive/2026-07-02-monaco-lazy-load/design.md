## Context

The UI is a Vite + React 19 single-page app. Routing lives in
`ui/src/App.tsx`; the admin area is mounted at `/admin` and rendered through
`ui/src/pages/Admin.tsx` with nested routes. Monaco is imported eagerly via
`import Editor from '@monaco-editor/react'` in exactly two components,
`ui/src/components/TemplateTabReadOnly.tsx` and
`ui/src/components/TemplateTabNew.tsx`, both reached only through the admin
template tabs (`ui/src/components/TemplateTabs.tsx`). Because these modules are
in the static import graph of the app entry, Vite bundles Monaco into the
initial chunk, so every visitor downloads it even though only admins editing
templates ever use it.

Current bundle is ~1.5 MB (~470 KB gzipped) with Monaco the dominant
contributor. Vite/Rollup performs automatic code splitting when a module is
reached through a dynamic `import()`, which is the lever this change pulls.

## Goals / Non-Goals

**Goals:**
- Remove Monaco from the initial JS bundle so non-admin and anonymous loads do
  not download it.
- Load Monaco on demand the first time an editor is rendered, with a loading
  fallback.
- Keep all existing read-only and editable template behaviour and JSON
  validation intact.
- Keep the test suite green, adapting tests for the now-async editor.

**Non-Goals:**
- Reducing the size of Monaco itself (e.g. custom Monaco builds, dropping
  languages) — out of scope.
- Changing any editor feature, theme, or option.
- Touching the API, worker, or infrastructure.
- A general route-splitting overhaul of the whole app — only what is needed to
  split Monaco out is in scope (admin-route splitting is an option, not a
  mandate).

## Decisions

### Decision: Split at the editor boundary with `React.lazy` + `Suspense`
Introduce a small shared wrapper (e.g. `ui/src/components/LazyMonaco.tsx`)
that does `const Editor = React.lazy(() => import('@monaco-editor/react'))`
and renders it inside a `<Suspense fallback={...}>`. `TemplateTabReadOnly` and
`TemplateTabNew` import this wrapper instead of `@monaco-editor/react`
directly. Because the only static path to Monaco becomes a dynamic `import()`,
Rollup emits Monaco as its own async chunk.

- **Why a shared wrapper over lazying in each component:** keeps the
  `Suspense` boundary and fallback consistent, avoids duplicating the lazy
  glue, and gives tests a single seam to target.
- **Why `React.lazy` over a route-only split:** the editor boundary is the
  precise consumer of Monaco; splitting here guarantees Monaco leaves the
  initial bundle regardless of how the admin pages are loaded. Route-level
  lazy loading of `Admin` (and the admin panels) is a complementary, optional
  enhancement that further shrinks the initial bundle by deferring the rest of
  the admin surface, but is not required to meet the core goal.

Alternatives considered:
- **Manual `manualChunks` / `splitVendorChunk` config:** would create a
  separate Monaco vendor chunk but it would still be referenced by the initial
  bundle (eagerly fetched), so it would not actually defer the download. Does
  not meet the goal.
- **Direct `import()` without `React.lazy`:** possible but `React.lazy` +
  `Suspense` is the idiomatic React pattern and gives a declarative fallback.

### Decision: Fallback is a lightweight placeholder sized to the editor box
Render a simple MUI-based placeholder (e.g. a subtle skeleton or a small
"Loading editor…" indicator) inside the existing editor container box so the
surrounding layout (split pane, labels, validation indicator, buttons) stays
stable while the chunk loads.

- **Why:** prevents layout shift and keeps the rest of the tab interactive.

### Decision: Preserve the editor's props and options unchanged
The wrapper forwards all props (`height`, `defaultLanguage`, `value`,
`onChange`, `options`, `theme`) straight through to `@monaco-editor/react`, so
read-only vs editable behaviour, debounced validation, and the deploy-dialog
preview are untouched.

### Decision: Make tests await the lazy editor
Tests currently `vi.mock('@monaco-editor/react', ...)` and query the mock
editor synchronously. With lazy loading the editor renders after a microtask,
so tests must switch synchronous `getBy*`/`getAllBy*` lookups of the editor to
`findBy*` (or wrap interactions in `await waitFor`). The existing module mock
of `@monaco-editor/react` continues to satisfy the dynamic import in the test
environment; if the wrapper is what is imported lazily, the mock target is the
wrapper's import specifier. No new test infrastructure is expected beyond
awaiting and confirming the dynamic import resolves under jsdom/Vitest.

- **Why:** lazy components resolve asynchronously; synchronous queries would
  race the editor mount and flake.

## Risks / Trade-offs

- **First-open latency for admins** → The first editor render now waits for a
  network fetch of the Monaco chunk. Mitigation: show the loading fallback so
  the wait is visible and non-blocking; admins open this screen rarely and the
  chunk is cached for the rest of the session. Optionally prefetch the chunk on
  admin navigation.
- **Test flakiness if queries stay synchronous** → Mitigation: convert the
  affected editor lookups to `findBy*`/`await` as part of this change and run
  the suite to confirm.
- **Suspense fallback flashing for cached chunk** → Mitigation: once loaded the
  chunk is cached, so subsequent mounts resolve immediately; the fallback only
  appears on the first, uncached load.
- **Mock-target drift** → If the lazy import points at the new wrapper rather
  than `@monaco-editor/react`, the existing `vi.mock` specifier must match the
  actually-imported module. Mitigation: keep the dynamic import pointed at
  `@monaco-editor/react` inside the wrapper, or update the mock specifier to
  the wrapper.

## Migration Plan

This is a client-side, behaviour-preserving change with no data or API impact.
Deployment is a normal UI build and release. Rollback is reverting the change;
there is no persistent state to migrate. Validate by building for production
and confirming Monaco is in a separate async chunk absent from the initial
bundle, and by exercising the admin template tabs to confirm editors load and
behave as before.

## Open Questions

- Should the admin route/pages also be route-level lazy-loaded in this change
  for additional initial-bundle savings, or deferred to a follow-up? (Core goal
  is met by editor-level splitting alone.)
- Should the Monaco chunk be prefetched when an admin navigates into the admin
  area to mask first-open latency?
