## 1. Database: Rename column

- [ ] 1.1 Create Alembic migration to rename `default_values_json` to `system_values_json` on `product_template_version` table using `op.alter_column(..., new_column_name=...)`
- [ ] 1.2 Verify migration works on both SQLite (tests) and Postgres (prod)

## 2. Backend: Rename model fields

- [ ] 2.1 In `api/app/models.py`: rename `default_values_json` to `system_values_json` on `ProductTemplateVersionBase` and `ProductTemplateVersionORM` (update `sa_column` mapping to point to renamed column)
- [ ] 2.2 Verify `ProductTemplateVersionRead` and `ProductTemplateVersionCreate` inherit the renamed field correctly

## 3. Backend: Update service references

- [ ] 3.1 In `api/app/services/reconcile.py`: rename `template.default_values_json` to `template.system_values_json` in `_build_merged_values()`
- [ ] 3.2 In `api/app/services/reconcile.py`: remove `_build_system_overrides()` method, pass `None` as third argument to `merge_values_scoped()`

## 4. Backend: Rename CLI flags

- [ ] 4.1 In `api/app/cli.py`: rename `--default-values-json` to `--system-values-json` and `--default-values-file` to `--system-values-file` in the create-template command
- [ ] 4.2 Update the `_parse_json_object_input` call to use the new option name

## 5. Backend: Update tests

- [ ] 5.1 In `api/tests/test_models_v2.py`: rename `default_values_json` to `system_values_json` in fixtures and assertions
- [ ] 5.2 In `api/tests/test_reconcile_service.py`: rename `default_values_json` to `system_values_json` in `_seed_deployment` helper
- [ ] 5.3 In `api/tests/test_cli.py`: update CLI flag from `--default-values-json` to `--system-values-json` and rename assertion field
- [ ] 5.4 Run full backend test suite to verify all tests pass

## 6. Frontend: Rename type and endpoint

- [ ] 6.1 In `ui/src/api/types.ts`: rename `default_values_json` to `system_values_json` on `ProductTemplate` interface
- [ ] 6.2 In `ui/src/api/endpoints.ts`: rename `default_values_json` to `system_values_json` in `createTemplate` payload type
- [ ] 6.3 In `ui/src/api/endpoints.test.ts`: rename fixture and assertion references

## 7. Frontend: Remove defaultValuesJson from deploy-flow components

- [ ] 7.1 In `ui/src/components/UserValuesForm.tsx`: remove `defaultValuesJson` prop from `UserValuesFormProps`, remove `flattenDefaults()` function, remove `defaults` memo, update `useEffect` to seed form fields using `field.default` only
- [ ] 7.2 In `ui/src/components/DeployDialogContent.tsx`: remove `defaultValuesJson` prop from `DeployDialogContentProps`, stop passing it to `UserValuesForm`
- [ ] 7.3 In `ui/src/components/DeployDialog.tsx`: stop passing `defaultValuesJson` to `DeployDialogContent`

## 8. Frontend: Update admin UI

- [ ] 8.1 In `ui/src/components/TemplateTabNew.tsx`: rename `default_values_json` to `system_values_json` in `onSave` payload type, `handleSave`, and pre-population from `newest.system_values_json`. Change "Default values" label to "System values". Stop passing `defaultValuesJson` to `DeployDialogContent` preview.
- [ ] 8.2 In `ui/src/components/TemplateTabReadOnly.tsx`: rename `template.default_values_json` to `template.system_values_json`. Change "Default values" label to "System values". Stop passing `defaultValuesJson` to `DeployDialogContent` preview.
- [ ] 8.3 In `ui/src/components/TemplateTabs.tsx`: rename `default_values_json` in `createTemplateMutation` payload type

## 9. Frontend: Update tests

- [ ] 9.1 In `ui/src/components/TemplateTabs.test.tsx`: rename `default_values_json` in `makeTemplate` helper
- [ ] 9.2 In `ui/src/components/TemplateTabNew.test.tsx`: rename in `existingTemplate` fixture and `onSave` assertion
- [ ] 9.3 In `ui/src/components/DeployDialog.test.tsx`: rename in `helloTemplate` fixture
- [ ] 9.4 In `ui/src/components/DeployDialogContent.test.tsx`: remove `defaultValuesJson` from test renders
- [ ] 9.5 In `ui/src/components/UserValuesForm.test.tsx`: remove `defaultValuesJson` from test renders, verify form fields seed from JSON Schema `default` annotations
- [ ] 9.6 Run full frontend test suite

## 10. Documentation

- [ ] 10.1 In `api/README.md`: update field reference from `default_values_json` to `system_values_json`
