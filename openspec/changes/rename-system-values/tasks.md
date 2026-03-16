## 1. Database: Rename column

- [x] 1.1 Create Alembic migration to rename `default_values_json` to `system_values_json` on `product_template_version` table using `op.alter_column(..., new_column_name=...)`
- [x] 1.2 Verify migration works on both SQLite (tests) and Postgres (prod)

## 2. Backend: Rename model fields

- [x] 2.1 In `api/app/models.py`: rename `default_values_json` to `system_values_json` on `ProductTemplateVersionBase` and `ProductTemplateVersionORM` (update `sa_column` mapping to point to renamed column)
- [x] 2.2 Verify `ProductTemplateVersionRead` and `ProductTemplateVersionCreate` inherit the renamed field correctly

## 3. Backend: Update service references

- [x] 3.1 In `api/app/services/reconcile.py`: rename `template.default_values_json` to `template.system_values_json` in `_build_merged_values()`
- [x] 3.2 In `api/app/services/reconcile.py`: remove `_build_system_overrides()` method, pass `None` as third argument to `merge_values_scoped()`

## 4. Backend: Rename CLI flags

- [x] 4.1 In `api/app/cli.py`: rename `--default-values-json` to `--system-values-json` and `--default-values-file` to `--system-values-file` in the create-template command
- [x] 4.2 Update the `_parse_json_object_input` call to use the new option name

## 5. Backend: Update tests

- [x] 5.1 In `api/tests/test_models_v2.py`: rename `default_values_json` to `system_values_json` in fixtures and assertions
- [x] 5.2 In `api/tests/test_reconcile_service.py`: rename `default_values_json` to `system_values_json` in `_seed_deployment` helper
- [x] 5.3 In `api/tests/test_cli.py`: update CLI flag from `--default-values-json` to `--system-values-json` and rename assertion field
- [x] 5.4 Run full backend test suite to verify all tests pass

## 6. Frontend: Rename type and endpoint

- [x] 6.1 In `ui/src/api/types.ts`: rename `default_values_json` to `system_values_json` on `ProductTemplate` interface
- [x] 6.2 In `ui/src/api/endpoints.ts`: rename `default_values_json` to `system_values_json` in `createTemplate` payload type
- [x] 6.3 In `ui/src/api/endpoints.test.ts`: rename fixture and assertion references

## 7. Frontend: Remove defaultValuesJson from deploy-flow components

- [x] 7.1 In `ui/src/components/UserValuesForm.tsx`: rename `defaultValuesJson` prop to `initialValuesJson` (still needed for edit mode pre-population), remove `defaults` memo name to `initialValues`
- [x] 7.2 In `ui/src/components/DeployDialogContent.tsx`: rename `defaultValuesJson` prop to `initialValuesJson`, pass through to `UserValuesForm`
- [x] 7.3 In `ui/src/components/DeployDialog.tsx`: pass `null` in create mode (no more `default_values_json`), pass `deployment.user_values_json` in edit mode via `initialValuesJson`

## 8. Frontend: Update admin UI

- [x] 8.1 In `ui/src/components/TemplateTabNew.tsx`: rename `default_values_json` to `system_values_json` in `onSave` payload type, `handleSave`, and pre-population from `newest.system_values_json`. Change "Default values" label to "System values". Stop passing system values to `DeployDialogContent` preview.
- [x] 8.2 In `ui/src/components/TemplateTabReadOnly.tsx`: rename `template.default_values_json` to `template.system_values_json`. Change "Default values" label to "System values". Stop passing system values to `DeployDialogContent` preview.
- [x] 8.3 In `ui/src/components/TemplateTabs.tsx`: rename `default_values_json` in `createTemplateMutation` payload type

## 9. Frontend: Update tests

- [x] 9.1 In `ui/src/components/TemplateTabs.test.tsx`: rename `default_values_json` in `makeTemplate` helper
- [x] 9.2 In `ui/src/components/TemplateTabNew.test.tsx`: rename in `existingTemplate` fixture and `onSave` assertion
- [x] 9.3 In `ui/src/components/DeployDialog.test.tsx`: rename in `helloTemplate` fixture
- [x] 9.4 In `ui/src/components/DeployDialogContent.test.tsx`: rename `defaultValuesJson` to `initialValuesJson` in test renders
- [x] 9.5 In `ui/src/components/UserValuesForm.test.tsx`: rename `defaultValuesJson` to `initialValuesJson` in test renders
- [x] 9.6 Run full frontend test suite

## 10. Documentation

- [x] 10.1 In `api/README.md`: update field reference from `default_values_json` to `system_values_json`
