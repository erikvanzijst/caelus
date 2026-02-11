# Caelus UI

React + TypeScript frontend for the Caelus API.

## Features
- User dashboard for deployments (create, list, delete, open).
- Admin area for products, template versions, and canonical template selection.
- Requests include `x-auth-request-email` to reflect the authenticated user (stored locally for dev).

## Requirements
- API running at `http://localhost:8000`
- Node 18+

## Setup
```bash
cd ui
npm install
```

## Run
```bash
npm run dev
```

Optional API override:
```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

## Build
```bash
npm run build
```

## Notes
- Products without a canonical template are hidden from deployment creation.
- Creating the first template for a product auto-sets it as canonical.
- Deleting the canonical template promotes the newest remaining template.
