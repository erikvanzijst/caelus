# Groups carry authorization; the realm carries authentication. One realm and
# one signup serve both environments, so nobody needs a second account — dev is
# closed by membership instead.
#
# Terraform owns the group *definitions* only. Memberships are administered in
# the Keycloak console (or by the seeding script) and are deliberately not
# declared here, so granting or revoking access needs no apply.

resource "keycloak_group" "freepod_dev" {
  realm_id = keycloak_realm.freepod.id
  name     = "freepod-dev"
}

resource "keycloak_group" "freepod_observability" {
  realm_id = keycloak_realm.freepod.id
  name     = "freepod-observability"
}
