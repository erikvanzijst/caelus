# Caelus UI

React + TypeScript + MUI frontend for the Caelus API.

This README is intentionally behavior-heavy so future agents can quickly orient themselves in the UI without re-discovering interaction details.

## Stack
- React 19 + TypeScript
- Vite
- MUI v7 (with custom theme)
- TanStack React Query
- MUI X DataGrid (community)
- React Router (`/`, `/admin/products`, `/admin/deployments`)

## Local Run
Requirements:
- Node 18+
- API running at `http://localhost:8000`

Install and run:
```bash
cd ui
npm install
npm run dev
```

Optional API URL override:
```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

Build:
```bash
npm run build
```

## App Structure
- `src/App.tsx`: route switch (`/` Dashboard, `/settings` and `/admin`, each with nested panel routes).
- `src/components/AppShell.tsx`: global layout shell, top app bar, nav buttons, signed-in chip, email switch button, decorative radial background, and email dialog gating.
- `src/components/EmailDialog.tsx`: modal to capture local dev email.
- `src/components/SectionSidebar.tsx`: collapsible section nav for a page composed of panels. Shared by Admin and Settings so the two cannot drift.
- `src/components/AdminSidebar.tsx`: the Admin page's nav items, over `SectionSidebar`.
- `src/components/SshKeysPanel.tsx`: the account's SSH public keys — list, add, revoke.
- `src/components/AddSshKeyDialog.tsx`: paste or drop a public key; maps the platform's error `code` to a readable message.
- `src/components/CopyButton.tsx`: copy-to-clipboard with a confirmation tick. Shared by the SFTP fields and the SSH key list.
- `src/components/DatabasePanel.tsx`: the deployment's database panel — identity, credential (masked, copyable without reveal) and quota state, with the same "renders nothing on a 404" shape as `SftpAccessPanel`.
- `src/components/DatabaseFields.tsx`: the presentational fields rendered by `DatabasePanel` (database name, role, masked password, usage against allowance, state).
- `src/components/DatabaseAccessDialog.tsx`: focused modal opened from the deployment card mirroring `SftpAccessDialog`.
- `src/components/ProductsPanel.tsx`: product/template management (extracted from Admin page).
- `src/components/DeploymentsPanel.tsx`: admin deployments table using MUI DataGrid with sortable columns.
- `src/components/DeploymentDialog.tsx`: deployment detail dialog with read-only form, metadata, upgrade, and delete actions with live polling.
- `src/components/NewProduct.tsx`: extracted component for product creation form with icon upload support.
- `src/components/IconInput.tsx`: icon upload component with preview and automatic client-side downscaling for oversized images.
- `src/pages/Dashboard.tsx`: user deployment creation + deployment cards.
- `src/pages/Admin.tsx`: admin layout shell with sidebar and `<Outlet>` for nested routes.
- `src/pages/Settings.tsx`: account settings shell, same shape as Admin. Available to every signed-in user.
- `src/api/client.ts`: request helpers with `ApiError` class carrying the HTTP status and the platform's machine-readable error `code`.
- `src/api/endpoints.ts`: endpoint wrappers.
- `src/state/useAuthEmail.ts`: localStorage-backed auth email hook.
- `src/utils/formatDate.ts`: local-time ISO timestamp formatting.
- `src/utils/deploymentStatus.ts`: deployment status color and transitional state helpers.
- `src/theme.ts`: color/typography/shape/component overrides.

## Global Layout And Visuals
- Top-level shell uses full-height page with a sticky translucent app bar.
- App bar sections:
  - Left: avatar `C`, title `Caelus Control`, subtitle `Provisioning cockpit`
  - Center: `Dashboard` and `Admin` nav buttons
  - Right: signed-in email chip + `Switch` button
- Main content is wrapped in `Container maxWidth="xl"` with generous vertical spacing.
- Global background is a soft radial gradient; shell also adds two blurred radial accent circles.
- Typography uses Space Grotesk / Space Mono, rounded controls, pill-shaped buttons.

## Auth Email Behavior
- All API requests may include `x-auth-request-email`.
- Email source is localStorage key: `caelus.auth.email`.
- First load with no stored email shows a blocking dialog (`Confirm your email`) and prevents dismissing with empty input.
- `Switch` re-opens the dialog to change email.

Important current behavior:
- `useAuthEmail()` is local state per hook call (not shared context).
- Updating email from `AppShell` does not immediately update `Dashboard`/`Admin` hook instances in the same render tree.
- In practice, after entering email in a fresh session, data queries on pages may remain disabled until full page reload/navigation remount.
- After reload, both routes initialize from localStorage and behave normally.

## Dashboard (`/`)
Headline:
- `Your applications`
- Subtext: launch and track environments

Deploy an applications Card:
- Product `Select` shows only products with `template_id` set (canonical template required).
- Domain `TextField` is free text.
- `Launch` button disabled when:
  - no current user
  - no deployable products
  - create mutation is pending
- Inline validation:
  - selected product without canonical template => explicit canonical-template error
- Helper text shows selected canonical template id.
- If no deployable products, info alert tells user to set canonical template in Admin.

Data behavior:
- On load with email:
  - fetch users (`GET /users`)
  - fetch products (`GET /products`)
  - if no user exists for email, auto-create (`POST /users`) then refetch users
  - fetch deployments for resolved user (`GET /users/{id}/deployments`)
- On launch:
  - `POST /users/{id}/deployments`
  - clears domain input
  - invalidates deployments query

Deployment cards:
- One card per deployment.
- Shows domain, product chip (via `deployment.desired_template.product.name`), created timestamp, and desired template id.
- Shows reconcile status chip from backend deployment state.
- Shows `last_reconcile_at` timestamp.
- Shows inline error alert if `last_error` is present.
- Actions:
  - `Open` uses `ensureUrl()` (adds `https://` if missing)
  - `Delete` shows `window.confirm('Delete this deployment?')`, then `DELETE /users/{id}/deployments/{deploymentId}`
  - while delete is pending/reconciling, action is disabled and label changes to `Deleting...`

Empty state:
- `No deployments yet` card with guidance text.

## Admin (`/admin`)
Headline:
- `Admin`
- Subtext: products, template versions, canonical selection

Layout:
- Left sidebar navigation with two sections: **Products** and **Deployments**.
- `/admin` redirects to `/admin/products` by default.
- Content area renders via React Router `<Outlet>`.

### Products (`/admin/products`)

Create product:
- Requires non-empty product name.
- Description optional.
- Icon upload: optional image file with client-side preview; oversized images are automatically scaled down before upload.
- On success: clears fields, invalidates products query.
- Uses multipart form upload to send product data + optional icon file atomically.

Products list:
- Each item shows name, description fallback, canonical template chip.
- Selected row gets highlighted background.
- On first load with products, first product auto-selects.

Selected product panel:
- Shows name, description, created timestamp (`—` fallback if none selected).
- `Delete product` uses confirm dialog and then delete mutation.

Create template version:
- Disabled when no product is selected.
- Chart reference required (`chart_ref`).
- Chart version required (`chart_version`).
- On success:
  - invalidates templates + products queries
  - if selected product had no canonical template, new template is auto-set canonical

Template versions list:
- Each template row shows id, `chart_ref:chart_version`, and created timestamp.
- Canonical template gets `Canonical` chip.
- Row actions:
  - `Set canonical` => updates product template id
  - `Delete` => confirm + delete mutation
- Canonical delete behavior:
  - after deleting canonical template, app fetches templates, sorts by newest `created_at`, and sets newest remaining template as canonical (if one exists)

Empty templates state:
- `No templates yet. Add the first version to unlock deployments.`

### Deployments (`/admin/deployments`)

Sortable DataGrid table listing all non-deleted deployments via `GET /api/deployments`.

Columns:
- **Product**: product name from applied or desired template
- **Hostname**: clickable link (`https://{hostname}`, opens in new tab)
- **Email**: deployment owner's email
- **Created**: local-time ISO timestamp
- **Status**: deployment status string
- **Up to date**: green check if `applied_template.id === applied_template.product.template_id`, yellow warning otherwise

Default sort: Created descending.

Row click opens a **DeploymentDialog** with:
- Read-only `DeployDialogContent` showing the deployment's user values (hostname field renders as plain text, no Free/Custom domain toggle)
- Metadata section: Owner, Created, Age (human-readable), Last reconciliation, Current template, Status
- **Delete** button (left, red): triggers `DELETE /users/{id}/deployments/{id}`, shows progress bar during `deleting` state, closes dialog and removes row when API returns 404
- **Upgrade** button (right): disabled when up to date, otherwise shows `Upgrade to #{canonicalId}`. Calls `PUT /users/{id}/deployments/{id}` with the product's canonical template ID. Shows progress bar during `provisioning` state.

Live polling:
- Dialog polls `GET /users/{id}/deployments/{id}` at 1s intervals while deployment is in a transitional state (`provisioning` or `deleting`).
- Each poll result patches the `admin-deployments` query cache via `setQueryData`, keeping the table row in sync without polling the full list.
- Polling stops when deployment reaches a terminal state.
- 404 response (deleted deployment) removes the row from cache and closes the dialog.

## API And Query Notes
- API base URL: `VITE_API_URL` or default `http://localhost:8000`.
- `requestJson` always sends `Content-Type: application/json`.
- `204` responses map to `null`.
- Error handling normalizes FastAPI `detail` values (including validation arrays) into readable messages. Errors throw `ApiError` (extends `Error`) with an `status` property carrying the HTTP status code.
- Query defaults:
  - `refetchOnWindowFocus: false`
  - `retry: 1`
  - `staleTime: 5000ms`
- Dashboard deployments query auto-polls every 3s while any deployment is in transitional states (`provisioning` or `deleting`).
- Admin deployment dialog polls a single deployment at 1s intervals during transitions, patching the list cache via `setQueryData`.

## Settings (`/settings`)

The first account-level surface: everything here belongs to the person rather
than to one deployment. Reachable from the account menu, available to **every**
signed-in user — it is not an administrative feature and must not read as one.

Structured as a section nav plus `<Outlet>`, the same shape `/admin` uses, so a
second account section is one nav entry and one route. `/settings` redirects to
`/settings/ssh-keys`.

### SSH keys panel

Lists each key by label, fingerprint (Space Mono, with a copy button), type and
date. **A key with no label is named by its fingerprint**, not by a placeholder
— the platform deliberately does not invent a label, and inventing one in the
client would be the same mistake one layer out.

Adding accepts a pasted key or a **dropped `.pub` file**; the whole dialog body
is the drop target, with a `browse` link so it is reachable by keyboard.

A dropped **private** key is refused outright rather than loaded into the
field. That is the one path where the private half can be kept out of the page
entirely, and putting it in a textarea would itself be displaying it. Pasted
private material can only be caught after the fact, so it warns and blocks
submission instead.

Rejections are selected from the platform's `code` — `duplicate_key`,
`key_too_short`, `private_key_material` and the rest — **never** by matching on
its prose, so a reworded message cannot collapse six distinct failures into one
generic error. An unrecognized code falls back to the platform's own message.

The panel never offers in-browser key generation; it points at `freepod key
add`, where the private half stays on the user's machine.

Deleting asks for confirmation naming the key and its consequence.

The dialog resets on exit rather than in a close handler: the panel closes it
directly after a successful add without passing through any cancel path, and
the component stays mounted throughout, so a per-handler reset leaves the next
open still holding the previous key.

## Database panel

A deployment whose product opts into relational storage gets a panel on the
deployment view — the same shape as the SFTP panel, mounted beside it. It
shows identity (database name, role), a credential (the password, masked by
default), and the database's health against its allowance.

The panel is its own component (`DatabasePanel`), composed into the page
rather than inlined.

## Manual QA Matrix
Use these checks after UI/API contract changes:

0. Settings reachability (non-admin):
   - sign in as a user without administrator privileges
   - expected: the account menu shows `Settings` and no `Admin`
   - expected: navigating directly to `/settings` renders the SSH keys panel

1. Template create (Admin):
   - open `/admin`, select a product
   - create template with `chart_ref=ghcr.io/example/foo`, `chart_version=1.2.3`
   - expected: request `POST /products/{id}/templates` returns `201`
   - expected: new row appears with `ghcr.io/example/foo:1.2.3`

2. Canonical template behavior:
   - set template canonical
   - expected: product chip updates to `Canonical template #{id}`

3. Template delete:
   - delete non-canonical template
   - expected: row removed and list refreshes
   - delete canonical template
   - expected: newest remaining template is auto-selected as canonical (if any)

4. Deployment create (Dashboard):
   - open `/`, pick product, configure user values (if required), click `Launch`
   - expected: request payload includes `desired_template_id` (not `template_id`)
   - expected: request payload does not include top-level `domainname`
   - expected: `POST /users/{id}/deployments` returns `201`
   - expected: new deployment card appears with correct product and desired template id

5. Deployment status visibility:
   - expected card fields: status chip, last reconcile timestamp
   - if backend sets `last_error`, expected inline error alert with readable message

6. Deployment delete UX:
   - click delete and confirm
   - expected button becomes `Deleting...` and disabled
   - expected polling refreshes card state while deleting

7. Admin deployments table:
   - open `/admin/deployments`
   - expected: sortable table with all non-deleted deployments
   - click a row: expected deployment dialog opens with read-only form and metadata
   - hostname links should open in new tab without triggering the dialog

8. Admin deployment upgrade:
   - open dialog for an outdated deployment (yellow warning icon)
   - expected: button shows `Upgrade to #N`
   - click upgrade: expected progress bar, status changes to `provisioning`, button disabled
   - expected: table row status updates in real time
   - on completion: button changes to `Up to date` (disabled)

9. Admin deployment delete:
   - open dialog, click Delete
   - expected: progress bar (secondary color), button shows `Deleting...`
   - expected: table row status updates to `deleting`
   - on completion: dialog closes, row removed from table

10. Validation error readability:
   - trigger invalid create payload (for example empty required template fields)
   - expected alert text is readable and not `[object Object]`

11. Database panel:
   - open a deployment whose product offers relational storage
   - expected: panel renders database name, role and a masked password
   - expected: password can be copied without first being revealed
   - expected: panel states that the database is reachable from the running app, not the reader's machine
   - open a deployment whose product does not offer relational storage
   - expected: no panel is rendered and no placeholder is shown
   - as an administrator, open another account's deployment
   - expected: every field is shown except the password, which the panel states is withheld — no error state, no reveal affordance that cannot work

## Product Icon Sizes

Product icons use a deliberate size hierarchy across contexts to reflect visual
importance and available space:

| Context                          | Size | Variant   | Notes                                           |
|----------------------------------|------|-----------|-------------------------------------------------|
| Product list (Admin)             | 48px | `rounded` | Compact list — scannable                        |
| Selected product detail (Admin)  | 64px | `rounded` | Detail view with edit badge overlay             |
| Deployment card (Dashboard)      | 64px | `rounded` | Primary dashboard content — instant recognition |

When adding icons to new contexts, pick a size that fits this hierarchy. List
items should stay at 48px or below; detail/card views should use 64px.

## Responsive Behavior
- Dashboard create form uses column layout on small screens, row layout on medium+.
- Admin left/right columns collapse into a single vertical flow on small screens.
- App bar content remains a single row; at very narrow widths it compresses tightly.

## Playwright Browser Testing (Local Dev)

In production (Kubernetes), authentication is handled by Keycloak via Traefik's
forward-auth middleware — no manual email setup is needed. In local dev mode,
however, the UI relies on a localStorage key for auth headers. When automating
the browser with Playwright MCP, always use `user@example.com` as the dev
email and follow this sequence to establish an authenticated session:

```
1. browser_navigate  →  http://localhost:5173
2. browser_evaluate  →  () => {
     localStorage.setItem('caelus.auth.headers',
       JSON.stringify({"X-Auth-Request-Email": "user@example.com"}));
     window.location.reload();
   }
3. browser_wait_for  →  text: "user@example.com"
4. browser_navigate  →  http://localhost:5173/admin  (or any target page)
5. browser_wait_for  →  text: "user@example.com"
```

**Why the wait is required:** Playwright's `goto()` resolves on the browser
`load` event, but React's auth cycle is async (mount → read localStorage →
`GET /api/me` → re-render). Without the wait, snapshots will show the
pre-auth state ("No email set", empty product lists, missing Admin link).
The `wait_for` on the email address ensures the full auth round-trip has
completed and the UI has re-rendered with user data.

**Why step 2 uses `reload()` instead of a second `navigate`:** Setting
localStorage after the React tree has mounted does not update the
`useState(getStoredAuthHeaders)` initializer. The reload forces a fresh
mount that picks up the new value synchronously.

## Known UI Caveats
- Auth email state is not globally shared; see the reload caveat in `Auth Email Behavior`.
