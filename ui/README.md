# Caelus UI

React + TypeScript + MUI frontend for the Caelus API.

This README is intentionally behavior-heavy so future agents can quickly orient themselves in the UI without re-discovering interaction details.

## Stack
- React 19 + TypeScript
- Vite
- MUI v7 (with custom theme)
- TanStack React Query
- React Router (`/`, `/admin`)

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
- `src/App.tsx`: route switch (`/` Dashboard, `/admin` Admin).
- `src/components/AppShell.tsx`: global layout shell, top app bar, nav buttons, signed-in chip, email switch button, decorative radial background, and email dialog gating.
- `src/components/EmailDialog.tsx`: modal to capture local dev email.
- `src/pages/Dashboard.tsx`: user deployment creation + deployment cards.
- `src/pages/Admin.tsx`: product/template management and canonical template management.
- `src/api/*`: request helpers and endpoint wrappers.
- `src/state/useAuthEmail.ts`: localStorage-backed auth email hook.
- `src/theme.ts`: color/typography/shape/component overrides.

## Global Layout And Visuals
- Top-level shell uses full-height page with a sticky translucent app bar.
- App bar sections:
  - Left: avatar `C`, title `Caelus Control`, subtitle `Provisioning cockpit`
  - Center: `Dashboard` and `Admin` nav buttons
  - Right: signed-in email chip + `Switch` button
- Main content is wrapped in `Container maxWidth="lg"` with generous vertical spacing.
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
- `Your deployments`
- Subtext: launch and track environments

Create Deployment Card:
- Product `Select` shows only products with `template_id` set (canonical template required).
- Domain `TextField` is free text.
- `Launch` button disabled when:
  - no current user
  - no deployable products
  - create mutation is pending
- Inline validation:
  - empty domain => `Enter a domain name to continue.`
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
- Shows domain, product chip (via `deployment.template.product.name`), created timestamp, template id.
- Actions:
  - `Open` uses `ensureUrl()` (adds `https://` if missing)
  - `Delete` shows `window.confirm('Delete this deployment?')`, then `DELETE /users/{id}/deployments/{deploymentId}`

Empty state:
- `No deployments yet` card with guidance text.

## Admin (`/admin`)
Headline:
- `Admin`
- Subtext: products, template versions, canonical selection

Two-column desktop layout (stacks on small screens):
- Left column:
  - `Create product` form
  - `Products` list (click to select product)
- Right column:
  - `Selected product` summary + `Delete product`
  - `Create template version` form
  - `Template versions` list for selected product

Create product:
- Requires non-empty product name.
- Description optional.
- On success: clears fields, invalidates products query.

Products list:
- Each item shows name, description fallback, canonical template chip.
- Selected row gets highlighted background.
- On first load with products, first product auto-selects.

Selected product panel:
- Shows name, description, created timestamp (`—` fallback if none selected).
- `Delete product` uses confirm dialog and then delete mutation.

Create template version:
- Disabled when no product is selected.
- Docker image URL optional (`null` allowed).
- On success:
  - invalidates templates + products queries
  - if selected product had no canonical template, new template is auto-set canonical

Template versions list:
- Each template row shows id, docker image URL fallback, created timestamp.
- Canonical template gets `Canonical` chip.
- Row actions:
  - `Set canonical` => updates product template id
  - `Delete` => confirm + delete mutation
- Canonical delete behavior:
  - after deleting canonical template, app fetches templates, sorts by newest `created_at`, and sets newest remaining template as canonical (if one exists)

Empty templates state:
- `No templates yet. Add the first version to unlock deployments.`

## API And Query Notes
- API base URL: `VITE_API_URL` or default `http://localhost:8000`.
- `requestJson` always sends `Content-Type: application/json`.
- `204` responses map to `null`.
- Error handling throws `detail` from API when present.
- Query defaults:
  - `refetchOnWindowFocus: false`
  - `retry: 1`
  - `staleTime: 5000ms`

## Responsive Behavior
- Dashboard create form uses column layout on small screens, row layout on medium+.
- Admin left/right columns collapse into a single vertical flow on small screens.
- App bar content remains a single row; at very narrow widths it compresses tightly.

## Known UI Caveats
- `GridLegacy` is still used and logs a deprecation warning in dev console.
- Auth email state is not globally shared; see the reload caveat in `Auth Email Behavior`.
