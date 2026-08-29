#!/bin/bash
# Validate the runtime configuration, render the server configuration from it,
# and only then start sshd. A misconfiguration must be a container that exits
# with an explanation, not one that runs and refuses every connection: the
# second is indistinguishable from a network fault and gets diagnosed as one.
set -euo pipefail

readonly PORT=2222
readonly AUTHORIZED_KEYS=/etc/ssh/authorized_keys
readonly SSHD_CONFIG=/etc/ssh/sshd_config
readonly SESSION_ENV=/etc/freepod/session-env
readonly HOST_KEY=/etc/ssh/ssh_host_ed25519_key

die() {
    echo "ssh-sidecar: $*" >&2
    exit 1
}

require() {
    local name=$1
    [[ -n ${!name:-} ]] || die "$name is not set. It is required; see the image README."
}

# --- trusted keys ----------------------------------------------------------
require FREEPOD_AUTHORIZED_KEYS

install -m 0600 /dev/null "$AUTHORIZED_KEYS"
keys=0
while IFS= read -r line; do
    [[ -n ${line//[[:space:]]/} ]] || continue
    [[ ${line#"${line%%[![:space:]]*}"} != \#* ]] || continue
    # ssh-keygen is the only authority on what sshd will accept. Parsing the
    # line ourselves would accept things sshd then silently ignores, leaving a
    # container that starts with a trust set nobody can use.
    if ! printf '%s\n' "$line" | ssh-keygen -l -f /dev/stdin >/dev/null 2>&1; then
        die "FREEPOD_AUTHORIZED_KEYS contains a line that is not a valid SSH public key."
    fi
    printf '%s\n' "$line" >> "$AUTHORIZED_KEYS"
    keys=$((keys + 1))
done <<< "$FREEPOD_AUTHORIZED_KEYS"

(( keys > 0 )) || die "FREEPOD_AUTHORIZED_KEYS contains no public key. Refusing to start a server nobody can authenticate to."

# --- forward allowlist -----------------------------------------------------
require FREEPOD_PERMIT_OPEN

permit_open=()
while read -r dest; do
    [[ -n $dest ]] || continue
    # host:port, or [v6addr]:port. No wildcard port: an allowlist entry that
    # opens every port on a host is not an allowlist (D6).
    if [[ ! $dest =~ ^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9._-]+):([0-9]{1,5})$ ]]; then
        die "FREEPOD_PERMIT_OPEN entry '$dest' is not host:port. Ports must be numeric; wildcards are not accepted."
    fi
    port=${BASH_REMATCH[2]}
    if (( port < 1 || port > 65535 )); then
        die "FREEPOD_PERMIT_OPEN entry '$dest' has a port outside 1-65535."
    fi
    permit_open+=("$dest")
done < <(tr ',[:space:]' '\n\n' <<< "$FREEPOD_PERMIT_OPEN")

(( ${#permit_open[@]} > 0 )) || die "FREEPOD_PERMIT_OPEN is empty. Forwarding must name at least one destination."

# --- release identity ------------------------------------------------------
# Required rather than optional: the banner exists so a developer investigating
# a broken release is not shown a working one during a rollout (D17), and a
# banner that cannot name its release is the failure it was added to prevent.
require FREEPOD_RELEASE_ID

# --- database connection details -------------------------------------------
# These reach the toolbox from the sidecar's own environment, never from the
# application process: a developer connects precisely when the application is
# broken, and details read from a crash-looping process are unavailable then.
for var in PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE; do
    require "$var"
done
[[ $PGPORT =~ ^[0-9]{1,5}$ ]] || die "PGPORT is not a port number."

# sshd hands a session a sanitized environment, so the container's own
# variables do not reach the dispatcher on their own. They are staged here in
# the same NUL-delimited form as /proc/<pid>/environ, which the dispatcher can
# read back without quoting or re-evaluating anything.
install -m 0600 /dev/null "$SESSION_ENV"
for var in PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE PGSSLMODE PGAPPNAME FREEPOD_RELEASE_ID; do
    [[ -n ${!var:-} ]] && printf '%s=%s\0' "$var" "${!var}" >> "$SESSION_ENV"
done

# --- host key --------------------------------------------------------------
# Per container, never persisted, Ed25519 only. An RSA 4096 key costs seconds
# on every start before anything listens, and buys nothing: the identity a
# developer verifies is the platform edge's, and the hop from the edge to here
# does not pin this key.
rm -f /etc/ssh/ssh_host_*
ssh-keygen -q -t ed25519 -N '' -C '' -f "$HOST_KEY"

# --- server configuration --------------------------------------------------
# Note what is absent: there is no ChrootDirectory. Chroot is incompatible with
# the forwarding this profile exists to provide -- the process that opens a
# forwarded connection inherits it and has no resolver configuration there, so
# the forward's target fails to resolve (D3).
{
    cat <<-CONFIG
	Port ${PORT}
	ListenAddress 0.0.0.0
	ListenAddress ::

	HostKey ${HOST_KEY}

	PubkeyAuthentication yes
	AuthenticationMethods publickey
	AuthorizedKeysFile ${AUTHORIZED_KEYS}
	PermitRootLogin prohibit-password
	PasswordAuthentication no
	KbdInteractiveAuthentication no
	PermitEmptyPasswords no
	UsePAM no
	PermitUserEnvironment no

	AllowTcpForwarding local
	AllowAgentForwarding no
	AllowStreamLocalForwarding no
	GatewayPorts no
	X11Forwarding no
	PermitTunnel no

	PermitUserRC no
	PrintMotd no
	PrintLastLog no
	ForceCommand /usr/local/bin/freepod-dispatch
	Subsystem sftp internal-sftp
	CONFIG
    printf 'PermitOpen %s\n' "${permit_open[*]}"
} > "$SSHD_CONFIG"
chmod 0600 "$SSHD_CONFIG"

/usr/sbin/sshd -t -f "$SSHD_CONFIG" || die "rendered sshd configuration was rejected by sshd -t."

echo "ssh-sidecar: release ${FREEPOD_RELEASE_ID}, ${keys} trusted key(s), forwarding to ${permit_open[*]}, listening on ${PORT}." >&2
exec /usr/sbin/sshd -D -e -f "$SSHD_CONFIG"
