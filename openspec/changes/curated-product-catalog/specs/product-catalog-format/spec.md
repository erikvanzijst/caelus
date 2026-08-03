## ADDED Requirements

### Requirement: Published products are declared as catalog files
The repository SHALL contain a top-level `products/catalog/` directory holding
one YAML file per published product, named `<slug>.yaml`. The `product.slug`
value inside a file MUST equal its filename stem, and slugs MUST be unique
across the catalog. A product's catalog file is the authoritative declaration of that
product's marketing metadata, chart reference, system values, and user values
schema.

#### Scenario: Catalog file declares a product
- **WHEN** `products/catalog/immich.yaml` exists with `product.slug: immich`
- **THEN** it SHALL be the authoritative declaration for the Immich product

#### Scenario: Slug does not match filename
- **WHEN** `products/catalog/immich.yaml` declares `product.slug: photos`
- **THEN** validation SHALL fail with an error identifying the mismatched file

#### Scenario: Duplicate slugs across files
- **WHEN** two catalog files declare the same `product.slug`
- **THEN** validation SHALL fail and identify both files

### Requirement: Catalog files carry a schema version
Each catalog file SHALL declare a top-level `schema_version` integer. The
reconciler MUST reject a file whose `schema_version` it does not recognize,
rather than applying a partially understood document.

#### Scenario: Recognized schema version
- **WHEN** a catalog file declares `schema_version: 1` and the reconciler
  supports version 1
- **THEN** the file SHALL be accepted for processing

#### Scenario: Unrecognized schema version
- **WHEN** a catalog file declares a `schema_version` the reconciler does not
  support
- **THEN** the reconciler SHALL reject the file with an error naming the file
  and the unsupported version

### Requirement: The product block declares catalog-managed product fields
Each catalog file SHALL contain a `product` block declaring `slug`, `name`,
`description`, `category`, `replaces`, and `icon`. These values are applied to
the corresponding `product` row fields on every reconciliation.

The block SHALL NOT declare `visibility`. Whether a product is offered to end
users is runtime state owned by the database and changed by administrators
directly, not part of the product's catalog definition.

#### Scenario: Product block is applied
- **WHEN** a catalog file declares `product.name: Immich` and
  `product.category: Photos & video`
- **THEN** the reconciled product row SHALL carry those values

#### Scenario: Declaring visibility is rejected
- **WHEN** a catalog file declares `product.visibility`
- **THEN** validation SHALL fail, because visibility is not a catalog-managed
  field

### Requirement: Icons are committed as image files inside the catalog directory
The `product.icon` value SHALL be a path to an image file, relative to the
catalog directory root, and that file MUST live inside the catalog directory so
that the directory remains a self-contained unit for `apply`, `lint`, and image
builds. Image data MUST NOT be embedded in the catalog document, so that icon
changes are reviewable as image diffs rather than as opaque encoded text. The
`icon` value MAY be omitted, in which case the product has no icon.

#### Scenario: Icon is referenced by path
- **WHEN** a catalog file declares `product.icon: icons/immich.png`
- **THEN** the image SHALL be read from `icons/immich.png` relative to the
  catalog directory root

#### Scenario: Embedded image data is rejected
- **WHEN** a catalog file supplies image bytes inline instead of a path
- **THEN** validation SHALL fail

#### Scenario: Icon path escaping the catalog directory is rejected
- **WHEN** a catalog file declares an `icon` path that resolves outside the
  catalog directory root
- **THEN** validation SHALL fail

#### Scenario: Product without an icon
- **WHEN** a catalog file omits `product.icon`
- **THEN** the file SHALL be valid and the reconciled product SHALL have no
  icon

### Requirement: The template block declares the deployable spec
Each catalog file SHALL contain a `template` block declaring exactly the fields
that constitute a template version: `chart_ref`, `chart_version`,
`chart_digest`, `system_values`, and `values_schema`. The `system_values` and
`values_schema` values SHALL be written to the template row verbatim, with no
templating or substitution, so that the file content is exactly what is applied
at deploy time. The pinned application image tag lives inside `system_values`.

#### Scenario: Template block maps to a template row
- **WHEN** a catalog file declares `template.chart_ref`,
  `template.chart_version`, and `template.system_values`
- **THEN** a reconciled template row SHALL carry those values in
  `chart_ref`, `chart_version`, and `system_values_json` respectively

#### Scenario: System values are applied verbatim
- **WHEN** `template.system_values` declares `image.tag: v3.0.3`
- **THEN** the template row's `system_values_json` SHALL contain
  `{"image": {"tag": "v3.0.3"}}` with no substitution applied

### Requirement: The upstream block declares release-detection metadata
Each catalog file SHALL contain an `upstream` block declaring `source`,
`match`, and `version_path`. `source` identifies where upstream releases are
published and MUST declare a `type` (such as `github-release` or
`docker-tag`) with its type-specific locator. `match` is a regular expression
selecting eligible upstream tags and MUST define a named capture group
`version` used to order candidates. `version_path` is a dotted path into the
catalog document identifying where the winning tag is written. The `upstream`
block is consumed only by release-detection tooling and SHALL NOT be applied to
the cluster or persisted on the template row.

#### Scenario: Upstream metadata selects and orders candidates
- **WHEN** `upstream.match` is `^v(?P<version>\d+\.\d+\.\d+)$` and upstream
  publishes tags `v3.0.3`, `v3.1.0`, and `v3.1.0-beta.1`
- **THEN** only `v3.0.3` and `v3.1.0` SHALL be eligible candidates
- **AND** `v3.1.0` SHALL be ordered ahead of `v3.0.3` by its `version` group

#### Scenario: Winning tag is written verbatim to version_path
- **WHEN** `upstream.version_path` is `system_values.image.tag` and the winning
  upstream tag is `33.0.7-apache`
- **THEN** release-detection tooling SHALL write `33.0.7-apache` verbatim to
  `template.system_values.image.tag`

#### Scenario: Upstream block is not persisted
- **WHEN** a catalog file containing an `upstream` block is reconciled
- **THEN** no part of the `upstream` block SHALL appear on the resulting
  template row
