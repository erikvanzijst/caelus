# Issue 031: Add user-configurable Helm values to deployment UI

## Depends On
`030-template-user-schema.md`

The deployment widget should allow the user to provide values for the `user_values_schema` of the canonical version
template.

The UI should parse the json schema and provide a form for the user to fill in.
This form should be validated against the schema, client-side.
