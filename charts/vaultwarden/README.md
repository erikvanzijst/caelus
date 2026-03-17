# Vaultwarden Helm Chart

We're using the unofficial Vaultwarden Helm chart from https://github.com/gissilabs/charts/tree/master/vaultwarden

Create a new Vaultwarden product in the Admin UI and add a template with the following values:

- Chart: https://github.com/gissilabs/charts/releases/download/vaultwarden-1.3.0/vaultwarden-1.3.0.tgz
- Tag: 1.3.0

Default values json:

```json
{
  "vaultwarden": {
    "smtp": {
      "host": "smtp.mailer.svc.cluster.local",
      "port": "25",
      "from": "vaultwarden@deprutser.be",
      "enabled": true,
      "security": "off"
    }
  },
  "persistence": {
    "enabled": true
  },
  "ingress": {
    "enabled": true
  }
}
```

User values schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "ingress": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "host": {
          "type": "string",
          "title": "Hostname",
          "description": "The fully qualified domain name used to access Vaultwarden (e.g. vw.example.com)"
        }
      }
    },
    "vaultwarden": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "allowSignups": {
          "type": "boolean",
          "title": "Allow open registration",
          "description": "Allow anyone to create an account. When disabled, only users who receive an invitation can sign up."
        },
        "allowInvitation": {
          "type": "boolean",
          "title": "Allow invited users to register",
          "description": "Allow users who have been invited by an admin to create an account, even when open registration is disabled."
        },
        "admin": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "enabled": {
              "type": "boolean",
              "title": "Enable admin portal",
              "description": "Activate the /admin web interface for server management, user invitations, and configuration."
            },
            "token": {
              "type": "string",
              "title": "Admin token",
              "description": "Password required to access the admin portal. Auto-generated if left empty."
            }
          }
        }
      }
    }
  }
}
```
