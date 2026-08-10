terraform {
  required_version = ">= 1.0"

  required_providers {
    # Required even though the provider configuration is inherited from the
    # root module: without this, Terraform resolves the local name `keycloak`
    # to the default source address `hashicorp/keycloak`, which does not exist.
    # Kept in lockstep with ../providers.tf, including the < 5.8.0 cap for
    # Keycloak 24 compatibility — see the note there.
    keycloak = {
      source  = "keycloak/keycloak"
      version = "~> 5.7.0"
    }
  }
}
