# The `groups` client scope.
#
# NOT a Keycloak built-in. Keycloak 24.0.5 ships ten default client scopes
# (acr, address, email, microprofile-jwt, offline_access, phone, profile,
# role_list, roles, web-origins); `groups` is absent from all of them. The one
# in the `master` realm was created by hand when Grafana was set up, which is
# exactly why it is on the `grafana` client and missing from `caelus-dev` — and
# therefore why group-based gating is not available to Freepod today. A fresh
# realm has nothing to attach, so the scope and its mapper are declared here.
resource "keycloak_openid_client_scope" "groups" {
  realm_id    = keycloak_realm.freepod.id
  name        = "groups"
  description = "Group membership, consumed by oauth2-proxy allowed_groups and Grafana"

  # Not an OAuth2 scope value clients request by name — it rides along as a
  # default scope, so keep it out of the `scope` claim. Mirrors `master`.
  include_in_token_scope = false
}

resource "keycloak_openid_group_membership_protocol_mapper" "groups" {
  realm_id        = keycloak_realm.freepod.id
  client_scope_id = keycloak_openid_client_scope.groups.id
  name            = "groups"
  claim_name      = "groups"

  # Emits bare names (`freepod-dev`) rather than paths (`/freepod-dev`).
  # oauth2-proxy's allowed_groups and Grafana's groups_attribute_path both
  # compare against bare names, so flipping this to true fails every login
  # closed. Verified as false on `master` today.
  full_path = false

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true

  # No add_to_token_introspection: the argument does not exist before provider
  # 5.8.0, and we are capped below that for Keycloak 24 compatibility (see
  # ../providers.tf). The resulting mapper leaves `introspection.token.claim`
  # unset, where `master` has it explicitly "true" — the one deliberate
  # difference from the mapper being replaced. It is inert here: nothing reads
  # the groups claim through token introspection. oauth2-proxy uses the ID
  # token and userinfo, Grafana the userinfo endpoint. If a future consumer
  # does need it, raising the provider cap is the fix.
}

locals {
  # Authoritative default client scope set for every client below. Matches the
  # Keycloak defaults for an OIDC client, plus `groups`. Anything not listed
  # here is removed from the client on apply.
  default_client_scopes = [
    "acr",
    "email",
    "profile",
    "roles",
    "web-origins",
    keycloak_openid_client_scope.groups.name,
  ]
}

resource "keycloak_openid_client_default_scopes" "freepod_prod" {
  realm_id       = keycloak_realm.freepod.id
  client_id      = keycloak_openid_client.freepod_prod.id
  default_scopes = local.default_client_scopes
}

resource "keycloak_openid_client_default_scopes" "freepod_dev" {
  realm_id       = keycloak_realm.freepod.id
  client_id      = keycloak_openid_client.freepod_dev.id
  default_scopes = local.default_client_scopes
}

resource "keycloak_openid_client_default_scopes" "grafana" {
  realm_id       = keycloak_realm.freepod.id
  client_id      = keycloak_openid_client.grafana.id
  default_scopes = local.default_client_scopes
}
