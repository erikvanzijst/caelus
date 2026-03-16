## Overview

```
BEFORE                                  AFTER
------                                  -----

ProductTemplateVersion                  ProductTemplateVersion
  .default_values_json     ---------->   .system_values_json

CLI                                     CLI
  --default-values-json    ---------->   --system-values-json
  --default-values-file    ---------->   --system-values-file

API (read + write models)               API (read + write models)
  default_values_json      ---------->   system_values_json

Frontend type                           Frontend type
  default_values_json      ---------->   system_values_json

DeployDialogContent                     DeployDialogContent
  defaultValuesJson prop   ---------->   (removed)

UserValuesForm                          UserValuesForm
  defaultValuesJson prop   ---------->   (removed)
  flattenDefaults()        ---------->   (removed)
  form seeds from defaults ---------->   form seeds from field.default only

Reconciler                              Reconciler
  _build_system_overrides  ---------->   (removed, was no-op)
  merge(defaults, user, system)  ---->   merge(system, user, None)
```

```
Reconciler merge chain (unchanged semantics):

  BEFORE: merge(default_values_json, user_values_json, _build_system_overrides())
                                                        ^^^^^^^^^^^^^^^^^^^^^^^^
                                                        always returns {}

  AFTER:  merge(system_values_json,  user_values_json,  None)
                ^^^^^^^^^^^^^^^^^                        ^^^^
                renamed                                  explicit no-op
```

```
Form field default value resolution:

  BEFORE:  flattenDefaults(defaultValuesJson)[field.path]  ??  field.default
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
           from template.default_values_json

  AFTER:   field.default
           ^^^^^^^^^^^^^
           from JSON Schema "default" annotation only
```

## ADDED Requirements

### Requirement: Rename default_values_json to system_values_json across all layers
The system MUST rename the `default_values_json` field to `system_values_json` in the database column, ORM model, API read/write models, CLI flags, frontend types, and all internal references. The reconciler merge semantics MUST remain unchanged.

#### Scenario: Database column rename
- **WHEN** the Alembic migration runs
- **THEN** the `default_values_json` column on the `product_template_version` table is renamed to `system_values_json` without data loss

#### Scenario: API read model uses new field name
- **WHEN** a client fetches a template via `GET /api/products/{id}/templates`
- **THEN** the response includes `system_values_json` (not `default_values_json`)

#### Scenario: API write model uses new field name
- **WHEN** a client creates a template via `POST /api/products/{id}/templates` with `system_values_json` in the payload
- **THEN** the template is created with the provided system values

#### Scenario: API rejects old field name
- **WHEN** a client sends a create-template request with `default_values_json` in the payload
- **THEN** the API rejects the request (due to `extra="forbid"` on the model)

#### Scenario: CLI uses renamed flags
- **WHEN** an admin runs `caelus create-template --system-values-json '{...}'`
- **THEN** the template is created with the provided system values

#### Scenario: CLI also accepts file flag
- **WHEN** an admin runs `caelus create-template --system-values-file values.json`
- **THEN** the template is created with values read from the file

#### Scenario: Reconciler merge semantics unchanged
- **WHEN** the reconciler builds merged Helm values for a deployment
- **THEN** it produces the same result as before: `deep_merge(template.system_values_json, deployment.user_values_json)`

### Requirement: Remove _build_system_overrides from reconciler
The `DeploymentReconciler._build_system_overrides()` method MUST be removed. The `_build_merged_values()` method MUST pass `None` as the third argument to `merge_values_scoped()`.

#### Scenario: Reconciler no longer calls _build_system_overrides
- **WHEN** the reconciler reconciles a deployment
- **THEN** `_build_merged_values()` calls `merge_values_scoped(template.system_values_json, deployment.user_values_json, None)`

### Requirement: Admin UI uses renamed field and labels
The admin template UI (`TemplateTabNew` and `TemplateTabReadOnly`) MUST use the field name `system_values_json` and display the label "System values" instead of "Default values".

#### Scenario: TemplateTabNew shows System values editor
- **WHEN** an admin views the New template tab
- **THEN** the Monaco editor is labeled "System values" and its contents are saved as `system_values_json`

#### Scenario: TemplateTabNew pre-populates from newest template
- **WHEN** the admin opens the New template tab and a previous template exists
- **THEN** the System values editor is pre-populated with the newest template's `system_values_json`

#### Scenario: TemplateTabReadOnly shows System values
- **WHEN** an admin views a read-only template tab
- **THEN** the Monaco editor is labeled "System values" and displays the template's `system_values_json`

## MODIFIED Requirements

### deploy-dialog-shared: DeployDialogContent props interface

#### Modified: DeployDialogContent drops defaultValuesJson prop
- The `DeployDialogContent` component MUST NOT accept a `defaultValuesJson` prop
- Callers that previously passed `defaultValuesJson` MUST stop passing it

### hostname-field-ui: UserValuesForm drops defaultValuesJson prop

#### Modified: UserValuesForm seeds form fields from JSON Schema defaults only
- The `UserValuesForm` component MUST NOT accept a `defaultValuesJson` prop
- The `flattenDefaults()` function MUST be removed
- Form field initial values MUST come from the JSON Schema `default` annotation on each field (`field.default`) only
- **WHEN** a schema field has `"default": "some-value"` in the JSON Schema
- **THEN** the form field is pre-populated with `"some-value"`
- **WHEN** a schema field has no `default` annotation
- **THEN** the form field starts empty (or `false` for booleans)

### admin-schema-preview: Template editors use system_values_json

#### Modified: Default values editor renamed
- The admin template UI MUST use the label "System values" instead of "Default values" for the system values Monaco editor
- The `onSave` payload MUST use the field name `system_values_json` instead of `default_values_json`
- The deploy dialog preview in both `TemplateTabNew` and `TemplateTabReadOnly` MUST NOT pass system values to `DeployDialogContent` (it no longer accepts the prop)
