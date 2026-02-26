# 030 - Add Template User Values JSONSchema to Admin UI

Helm charts usually have values that the deployer can override. Caelus supports this. On its ProductTemplateVersion, it
has:

1. the Helm chart URL: `oci://registry.home:80/helm/hello-static`
2. Helm chart tag: `0.1.2`
3. values_schema_json: a JSONSchema that defines the subset of Helm values that the deployer can override.
4. default_values_json: a JSON object that defines the default values for the Helm values.

For example:

```json
{
  "chart_ref": "oci://registry.home:80/helm/hello-static",
  "chart_version": "0.1.2",
  "values_schema_json": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "ingress": {
        "type": "object",
        "properties": {
          "host": {
            "title": "domainname",
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "pattern": "^((?!-))(xn--)?[a-z0-9][a-z0-9-_]{0,61}[a-z0-9]{0,1}\\.(xn--)?([a-z0-9\\-]{1,61}|[a-z0-9-]{1,30}\\.[a-z]{2,})$",
            "description": "The domainname for the new application"
          }
        },
        "required": ["host"],
        "additionalProperties": false
      },
      "user": {
        "type": "object",
        "properties": {
          "message": {
            "type": "string",
            "maxLength": 2000,
            "description": "Text rendered in the generated index.html"
          }
        },
        "additionalProperties": false
      }
    },
    "required": ["ingress"],
    "additionalProperties": false
  },
  "default_values_json": {
    "user": {
      "message": "Hello World!"
    }
  }
}
```

The above template API object contains a JSONSchema with `ingress.host` and `user.message` attributes that the deployer
can override at deploy time.

Currently, the Admin UI does not support this and does not let the admin provide a json schema for the values. This
needs to be added to the Admin UI.

Acceptance Criteria:
1. The Admin UI should allow the deployer to provide a JSONSchema for the values.
2. The Admin UI should validate the JSONSchema.
3. The Admin UI should show the JSONSchema in the UI.
4. If feasible, the schema should be rendered in an editor with json syntax highlighting.
5. The schema must be included in template POST and PUT requests as the `values_schema_json` field.
