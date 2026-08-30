## 1. Link checking (lands first, per design.md § Migration Plan)

- [ ] 1.1 Write `scripts/check-doc-links.py`: for every tracked `*.md`
      (excluding `ui/node_modules/`), resolve each relative markdown link
      target against the linking file's directory and exit non-zero listing
      every target that does not exist. Verify by running it against the
      current tree — it must pass — and again with a deliberately broken link
      added, where it must fail naming that file and line.
- [ ] 1.2 Add a `docs-links` job to `.github/workflows/ci.yml` that checks out
      the repo and runs `scripts/check-doc-links.py`. Verify the job appears in
      the workflow's job list and that `python3 scripts/check-doc-links.py`
      succeeds locally with no network access.

## 2. `AGENTS.md` Architecture Notes (design.md § D7 — highest leverage)

- [ ] 2.1 Audit the 80-line Architecture Notes section into design.md § D6's
      three buckets, recording the bucket per paragraph in the change's
      scratch notes. Verify every paragraph is assigned before editing.
- [ ] 2.2 Rewrite Architecture Notes as terse entries plus links: builds
      (`build-api`, `build-data-model`, `build-execution`, `build-worker`),
      account SSH keys (`ssh-key-api`, `ssh-key-data-model`), vars
      (`deployment-vars-api`, `deployment-vars-data-model`,
      `deployment-vars-schema-routing`, `deployment-vars-reconciliation`),
      relational storage (`deployment-relational-storage`,
      `tenant-database-cluster`), the keyring, and curated products
      (`product-catalog-format`, `catalog-reconciliation`,
      `curated-product-governance`). Replace the five `See api/README.md § …`
      pointers with links into `openspec/`. Verify `scripts/check-doc-links.py`
      passes and the two-CLIs distinction (`caelus` vs `freepod`) survives —
      it is bucket 2 and spans capabilities.

## 3. `api/README.md` (~1,280 of 1,501 lines in scope)

- [ ] 3.1 Audit all 28 sections into the three buckets; confirm § Codebase Map,
      § Request Flow, § Local Development, § Database and Migrations,
      § Testing Strategy, § Error Handling, § Logging and § First 30 Minutes
      for a New Agent are bucket 2 and stay. Verify the bucket assignment
      covers every section.
- [ ] 3.2 Convert § Authentication (285 lines) → `auth-header-integration`,
      `oauth2-token-auth`, `oauth2-proxy-deployment`, `keycloak-deployment`,
      `authorization-guards`, `user-endpoint-authorization`,
      `product-endpoint-authorization`. Keep the production `skip-auth`
      footgun subsection if the audit finds it is bucket 2 or 3. Verify links
      resolve and the section is a terse entry plus links.
- [ ] 3.3 Convert § Builds (171 lines) → `build-api`, `build-artifact-upload`,
      `build-data-model`, `build-execution`, `build-worker`. Verify links
      resolve.
- [ ] 3.4 Convert § Product Catalog (170 lines) → `product-catalog-format`,
      `catalog-reconciliation`, `catalog-cli`, `curated-product-governance`,
      `product-visibility`. Verify links resolve.
- [ ] 3.5 Convert § Account SSH Keys (130 lines) → `ssh-key-api`,
      `ssh-key-data-model`, plus
      `openspec/changes/archive/2026-08-28-account-ssh-keys/design.md`.
      Verify the fingerprint measurement is reachable from the README in one
      hop — this is design.md § Context's worked example.
- [ ] 3.6 Convert § Per-Deployment Relational Storage (108) and § Reading a
      Deployment's Database Connection Details (7) →
      `deployment-relational-storage`, `tenant-database-cluster`,
      `relational-storage-chart-contract`, `database-credentials-api`,
      `database-housekeeping-worker`. Verify links resolve.
- [ ] 3.7 Convert § Core Data Model (108) → the data-model capabilities
      (`build-data-model`, `deployment-vars-data-model`,
      `deployment-release-ledger`, `plan-data-model`,
      `subscription-data-model`, `mollie-payment-data-model`,
      `ssh-key-data-model`). Verify links resolve.
- [ ] 3.8 Convert § Deployment Vars (107) → `deployment-vars-api`,
      `deployment-vars-data-model`, `deployment-vars-schema-routing`,
      `deployment-vars-reconciliation`. Verify links resolve.
- [ ] 3.9 Convert § API and CLI Parity (73), § Deployment Lifecycle and State
      Transitions (39), § Per-Deployment Object Storage (37), § Reconcile Queue
      Semantics (30) and § Product Icon and Static File Serving (26) →
      `deployment-create-contract`, `deployment-release-api`,
      `deployment-naming`, `deployment-namespace`, `deployment-object-storage`,
      `garage-bucket-provisioning`, `object-storage-chart-contract`,
      `worker-process-pool`, `product-marketing-metadata`. Verify links
      resolve.
- [ ] 3.10 Re-run `scripts/check-doc-links.py` and read the rewritten file end
      to end. Verify it still answers "where do I start" for a new
      contributor without opening a spec.

## 4. `cli/DEVELOPMENT.md` (~820 of 1,099 lines in scope)

- [ ] 4.1 Audit all 22 sections into the three buckets; confirm § Working in
      this package, § Module map, § Packing, § Testing, § CI and releasing and
      § Known wrinkles are bucket 2. Verify every section is assigned.
- [ ] 4.2 Generalize the existing preamble (lines 12–21) — which already names
      the `cli-*` capabilities and the originating design document — into the
      form design.md § D1 prescribes, and make it the file's link index.
      Verify it lists every `cli-*` capability that exists.
- [ ] 4.3 Convert § Authentication (99), § The command surface (73), § Reading
      logs (72), § The deploy pipeline (65), § `freepod db status` (58), § The
      project file (51), § Vars (50), § Deleting a deployment (40), § The build
      history (37), § Builds (37), § The API status-code contract (36), § The
      release history (27) and § Terms of Service (25) → the matching `cli-*`
      capabilities plus `openspec/changes/archive/2026-08-15-add-freepod-cli/
      design.md` for the numbered decisions the source comments cite. Verify
      every `D<n>` reference in `cli/src/` still resolves to a linked document.
- [ ] 4.4 Re-run `scripts/check-doc-links.py`. Verify `cli/README.md` is
      untouched (`git diff --stat` shows no change to it) — it is out of scope
      per design.md § Non-Goals.

## 5. `ui/README.md` (~240 of 390 lines in scope)

- [ ] 5.1 Convert § Admin (74), § Dashboard (42), § Settings (41) and
      § Database panel (10) → `admin-users-panel`, `admin-product-detail`,
      `admin-template-tabs`, `admin-schema-preview`,
      `admin-list-deployments-endpoint`, `deploy-dialog-shared`,
      `edit-deployment-frontend`, `account-settings-ui`,
      `database-credentials-ui`, `sftp-credentials-ui`, `hostname-field-ui`,
      `deploy-tos-consent-ui`. Verify links resolve.
- [ ] 5.2 Decide § Manual QA Matrix (73 lines): it is a test procedure, not a
      spec restatement, so it is bucket 2 and stays — but check each row for
      restated acceptance criteria that a spec scenario already carries and
      link those. Verify the matrix is still runnable by hand afterward.
- [ ] 5.3 Re-run `scripts/check-doc-links.py`. Verify § Stack, § Local Run,
      § App Structure and § Playwright Browser Testing are unchanged.

## 6. `tf/README.md`

- [ ] 6.1 Convert § Build subsystem (14) and § Tenant database cluster (8) →
      `build-worker`, `build-execution`, `tenant-database-cluster`. Verify
      § Secrets (126 lines, operational) is unchanged.

## 7. Close-out

- [ ] 7.1 Resolve design.md § Open Questions: confirm the root `README.md` and
      `k8s/README.md` need no entry, or convert them. Record the answer in the
      change before archiving.
- [ ] 7.2 Run `scripts/check-doc-links.py` over the whole tree and confirm the
      `docs-links` CI job passes on the branch. Verify zero unresolved links.
- [ ] 7.3 Confirm no bucket-3 content was lost: for each document, diff the
      removed prose against the specs and design documents it was replaced by
      and verify every relocated paragraph landed somewhere.
- [ ] 7.4 Report the final line counts per document against the ~2,400-line
      estimate in proposal.md § Impact, and note any section that stayed long
      because it was bucket 2.
