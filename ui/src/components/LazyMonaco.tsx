import { lazy, Suspense } from 'react'
import { Skeleton } from '@mui/material'
import type { EditorProps } from '@monaco-editor/react'

/**
 * Monaco is by far the largest contributor to the initial JS bundle, yet it is
 * only ever rendered on the admin template tabs. Loading it via a dynamic
 * `import()` turns the sole static path to Monaco into a code-split boundary, so
 * Rollup emits it as a separate async chunk that the browser fetches on demand
 * the first time an editor mounts — keeping it out of every non-admin load.
 */
const Editor = lazy(() => import('@monaco-editor/react'))

/**
 * Placeholder shown while the Monaco chunk downloads. It fills the editor's
 * container so the surrounding layout (split pane, labels, buttons) stays put
 * and does not shift when the real editor swaps in.
 */
function EditorFallback() {
  return (
    <Skeleton
      variant="rectangular"
      width="100%"
      height="100%"
      sx={{ minHeight: 100 }}
      data-testid="monaco-loading"
    />
  )
}

/**
 * Drop-in replacement for `@monaco-editor/react`'s default export that defers
 * loading Monaco. All editor props are forwarded unchanged, so read-only vs
 * editable behaviour, options, theme, and change handlers are untouched.
 */
export function LazyMonaco(props: EditorProps) {
  return (
    <Suspense fallback={<EditorFallback />}>
      <Editor {...props} />
    </Suspense>
  )
}
