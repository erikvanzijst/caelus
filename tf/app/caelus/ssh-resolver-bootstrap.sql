-- The SSH auth resolver's database role, applied on every rollout.
--
-- The resolver answers sshpiper's per-connection question -- may this key open
-- the deployment this username names -- from two tables and nothing else. It
-- sits on an internet-facing authentication path, so it connects as this role
-- rather than as the platform's own: a bug in it cannot write, and cannot read
-- a table it was never given.
--
-- Idempotent by construction, because it runs again on every rollout. It runs
-- *after* `alembic upgrade head`, since a grant needs the table to exist.
--
-- Required psql variables:
--   ssh_resolver_password    password for the caelus_ssh_resolver role

\set ON_ERROR_STOP on

SET client_min_messages = warning;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'caelus_ssh_resolver') THEN
        CREATE ROLE caelus_ssh_resolver LOGIN;
    END IF;
END
$$;

ALTER ROLE caelus_ssh_resolver WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS
    PASSWORD :'ssh_resolver_password';

-- Converge rather than accumulate: whatever this role was granted before, a
-- rollout takes it back and re-grants exactly the two tables below. Without
-- this, a grant added by hand during an incident would outlive the incident.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM caelus_ssh_resolver;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM caelus_ssh_resolver;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM caelus_ssh_resolver;

GRANT USAGE ON SCHEMA public TO caelus_ssh_resolver;

-- The whole grant. `deployment` answers where the username goes and whether it
-- is reachable; `user_ssh_key` answers whether the offered key is registered on
-- the account that owns it. Nothing else is read, so nothing else is granted --
-- deliberately including `user`, whose email addresses the resolver has no use
-- for, and `deployment_var`, whose values are the tenants' own.
--
-- No ALTER DEFAULT PRIVILEGES: a table added later must be granted here on
-- purpose, not inherited by a role that sits on the authentication path.
GRANT SELECT ON TABLE deployment TO caelus_ssh_resolver;
GRANT SELECT ON TABLE user_ssh_key TO caelus_ssh_resolver;
