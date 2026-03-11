## 1. Authorization Dependencies

- [ ] 1.1 Add `require_admin` dependency function to `api/app/deps.py` — chains off `get_current_user`, raises HTTPException(403, "Forbidden") if not `is_admin`, returns UserORM
- [ ] 1.2 Add `require_self` dependency function to `api/app/deps.py` — accepts `user_id: int` (auto-resolved from path), chains off `get_current_user`, raises HTTPException(403, "Forbidden") if `user_id != current_user.id` and not admin, returns UserORM

## 2. User & Deployment Endpoint Authorization

- [ ] 2.1 Update `list_users` and `create_user` in `api/app/api/users.py` to use `Depends(require_admin)` instead of `Depends(get_current_user)`
- [ ] 2.2 Disable `delete_user_endpoint` — replace implementation with `raise HTTPException(status_code=501, detail="User deletion is not yet implemented")`
- [ ] 2.3 Update `get_user` and all deployment endpoints (`create_deployment`, `list_deployments`, `get_deployment`, `update_deployment`, `delete_deployment_endpoint`) to use `Depends(require_self)`
- [ ] 2.4 Rename `_current_user` to `current_user` on endpoints that now use the dependency return value; update imports to include `require_admin` and `require_self`

## 3. Product & Template Endpoint Authorization

- [ ] 3.1 Update mutation endpoints in `api/app/api/products.py` to use `Depends(require_admin)`: `create_product`, `update_product`, `delete_product_endpoint`, `create_template`, `delete_template_endpoint`, `upload_icon`
- [ ] 3.2 Verify all GET endpoints (`list_products`, `get_product`, `list_templates`, `get_template`, `get_icon_redirect`) keep `Depends(get_current_user)`
- [ ] 3.3 Update imports and rename `_current_user` to `current_user` where appropriate

## 4. Authorization Tests

- [ ] 4.1 Add test fixtures/helpers for creating admin users, regular users, and setting auth headers in the test client
- [ ] 4.2 Add parameterized authorization tests covering the (endpoint, method) × (admin, self, other_user) matrix with expected status codes
- [ ] 4.3 Add specific test for DELETE /api/users/{user_id} returning 501 for all user types
- [ ] 4.4 Run full test suite and verify all existing tests still pass with the new authorization in place
