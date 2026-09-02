#!/usr/bin/env bash
#
# The ssh-sidecar test harness. Needs docker, ssh and bash, and no cluster:
# `docker run --pid=container:<name>` reproduces the shared process namespace a
# pod provides, which is what lets these tests prove the production behavior
# rather than an approximation of it.
#
#   ./run-tests.sh                      # build the image from ../ and test it
#   ./run-tests.sh --image REF          # test an already-built or pulled image
#
# Every negative case here is a security property rather than a feature, so a
# skipped one is a hole: they are asserted, not assumed.
set -uo pipefail

cd "$(dirname "$0")" || exit 1
readonly CONTEXT=..
readonly PREFIX=freepod-sshtest
# The account the SSH edge authenticates the upstream leg as: the deployment
# name, not "root". The sidecar adds it as a second uid-0 account, because the
# edge has one username convention and is ignorant of access profiles.
readonly LOGIN_USER=custom-user-app-harness
readonly NET=$PREFIX-net
readonly APP_IMAGE=$PREFIX/app
readonly NOSHELL_IMAGE=$PREFIX/noshell
readonly PG_IMAGE=postgres:18-alpine
readonly BUSYBOX_IMAGE=busybox:latest

IMAGE=""
while (( $# )); do
    case $1 in
        --image) IMAGE=${2:?--image needs a reference}; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

WORK=$(mktemp -d)
PASS=0
FAIL=0
FAILED_NAMES=()

cleanup() {
    local c
    for c in "${CONTAINERS[@]:-}"; do
        [[ -n $c ]] && docker rm -f "$c" >/dev/null 2>&1
    done
    [[ -n ${SELF_CONTAINER:-} ]] && docker network disconnect "$NET" "$SELF_CONTAINER" >/dev/null 2>&1
    docker network rm "$NET" >/dev/null 2>&1
    rm -rf "$WORK"
}
trap cleanup EXIT
CONTAINERS=()

run_container() { CONTAINERS+=("$1"); docker rm -f "$1" >/dev/null 2>&1; docker run -d --name "$@" >/dev/null; }

# --- assertions ------------------------------------------------------------
ok()   { PASS=$((PASS + 1)); printf '  \033[32mok\033[0m   %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); FAILED_NAMES+=("$1"); printf '  \033[31mFAIL\033[0m %s\n       %s\n' "$1" "$2"; }
group(){ printf '\n\033[1m%s\033[0m\n' "$1"; }

expect_eq()       { [[ $2 == "$3" ]] && ok "$1" || bad "$1" "expected '$2', got '$3'"; }
expect_contains() { [[ $3 == *"$2"* ]] && ok "$1" || bad "$1" "expected to contain '$2', got '$3'"; }
expect_missing()  { [[ $3 != *"$2"* ]] && ok "$1" || bad "$1" "expected NOT to contain '$2', got '$3'"; }
expect_nonzero()  { (( $2 != 0 )) && ok "$1" || bad "$1" "expected a non-zero exit, got 0"; }
expect_zero()     { (( $2 == 0 )) && ok "$1" || bad "$1" "expected exit 0, got $2"; }

# --- connectivity ----------------------------------------------------------
# Ordinarily the daemon and the ssh client share a host and a published port on
# 127.0.0.1 is the endpoint. When this harness runs inside a container on the
# same daemon -- a devcontainer, say -- published ports land on the daemon's
# host and are unreachable from here, so the harness joins the test network and
# addresses containers directly instead.
SELF_CONTAINER=""
if [[ -f /.dockerenv ]] && docker inspect "$(hostname)" >/dev/null 2>&1; then
    SELF_CONTAINER=$(hostname)
fi

# One word per line: `mapfile` splits on newlines, so emitting the flag and its
# value together would hand `docker run` a single argument with a space in it.
publish_args() {
    [[ -n $SELF_CONTAINER ]] && return 0
    printf '%s\n' --publish 127.0.0.1:0:2222
}

# Prints "<host> <port>" for the container that owns the sidecar's network.
endpoint_of() {
    local owner=$1
    if [[ -n $SELF_CONTAINER ]]; then
        echo "$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$owner") 2222"
    else
        local hostport
        hostport=$(docker port "$owner" 2222/tcp | head -1)
        echo "${hostport%:*} ${hostport##*:}"
    fi
}

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
          -o LogLevel=ERROR -o BatchMode=yes -o ConnectTimeout=10)

# ssh_to <owner-container> [ssh options] [command] -- logs in as root. The edge
# actually authenticates as the deployment name, which is a second uid-0 account
# the entrypoint adds; the test above this group's first case proves that
# account works, and the rest use root because the two are the same uid.
# Leading dash arguments are
# ssh's; everything after them is the remote command, which must follow the
# host on the command line.
ssh_to() {
    local owner=$1; shift
    local opts=()
    while [[ ${1:-} == -* ]]; do opts+=("$1"); shift; done
    local host port; read -r host port <<< "$(endpoint_of "$owner")"
    ssh -n "${SSH_OPTS[@]}" "${opts[@]}" -i "$WORK/id" -p "$port" "root@$host" "$@"
}

wait_for_port() {
    local owner=$1 deadline=$((SECONDS + 30)) host port
    while (( SECONDS < deadline )); do
        read -r host port <<< "$(endpoint_of "$owner")"
        if [[ -n $host && -n $port ]] && (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null; then
            return 0
        fi
        sleep 0.3
    done
    return 1
}

# http_get <host> <port> -- avoids a curl dependency; bash is already required.
http_get() {
    local host=$1 port=$2
    exec 3<>"/dev/tcp/$host/$port" || return 1
    printf 'GET / HTTP/1.0\r\nHost: t\r\n\r\n' >&3
    timeout 5 cat <&3
    exec 3<&- 3>&-
}

# sidecar_env <release-id> -- the runtime configuration contract, in one place.
sidecar_env() {
    printf '%s\n' \
        --env "FREEPOD_AUTHORIZED_KEYS=$(cat "$WORK/id.pub")" \
        --env "FREEPOD_PERMIT_OPEN=$PREFIX-allowed:8080 localhost:8080" \
        --env "FREEPOD_RELEASE_ID=$1" \
        --env "FREEPOD_LOGIN_USER=$LOGIN_USER" \
        --env "PGHOST=$PREFIX-pg" --env PGPORT=5432 \
        --env PGUSER=appuser --env PGPASSWORD=harness-secret --env PGDATABASE=appdb
}

# sidecar_env_nodb <release-id> -- the same contract for a product with no
# relational storage: no database variables, and consequently nothing to
# forward to either. The toolbox is a facility this image offers, not a
# precondition it imposes, so this configuration must produce a server that
# starts and serves the session paths unchanged.
sidecar_env_nodb() {
    printf '%s\n' \
        --env "FREEPOD_AUTHORIZED_KEYS=$(cat "$WORK/id.pub")" \
        --env "FREEPOD_RELEASE_ID=$1" \
        --env "FREEPOD_LOGIN_USER=$LOGIN_USER"
}

# --- setup -----------------------------------------------------------------
echo "building test fixtures..."
if [[ -z $IMAGE ]]; then
    IMAGE=$PREFIX/sidecar
    docker build -q --platform linux/amd64 -t "$IMAGE" "$CONTEXT" >/dev/null || { echo "sidecar build failed" >&2; exit 1; }
fi
docker build -q -f Dockerfile.app -t "$APP_IMAGE" . >/dev/null || exit 1
docker build -q -f Dockerfile.noshell -t "$NOSHELL_IMAGE" . >/dev/null || exit 1
echo "testing image: $IMAGE"

ssh-keygen -q -t ed25519 -N '' -C harness -f "$WORK/id"
ssh-keygen -q -t ed25519 -N '' -C intruder -f "$WORK/intruder"

docker network rm "$NET" >/dev/null 2>&1
docker network create "$NET" >/dev/null
[[ -n $SELF_CONTAINER ]] && docker network connect "$NET" "$SELF_CONTAINER" >/dev/null

mapfile -t PUBLISH < <(publish_args)

run_container "$PREFIX-pg" --network "$NET" \
    -e POSTGRES_USER=appuser -e POSTGRES_PASSWORD=harness-secret -e POSTGRES_DB=appdb "$PG_IMAGE"
for target in allowed denied; do
    run_container "$PREFIX-$target" --network "$NET" "$BUSYBOX_IMAGE" \
        sh -c "mkdir -p /www && echo forward-target-$target > /www/index.html && httpd -f -p 8080 -h /www"
done

run_container "$PREFIX-app" --network "$NET" "${PUBLISH[@]}" \
    -e APP_ONLY_VAR=from-the-application "$APP_IMAGE"
mapfile -t SIDE_ENV < <(sidecar_env release-7-uuid)
run_container "$PREFIX-side" --pid="container:$PREFIX-app" --network "container:$PREFIX-app" \
    --cap-add SYS_PTRACE "${SIDE_ENV[@]}" "$IMAGE"

# A sidecar with no shared process namespace and no application beside it: the
# state a developer meets when their pod is broken, and the one in which the
# database toolbox and forwarding must still work.
run_container "$PREFIX-lone" --network "$NET" "${PUBLISH[@]}" "${SIDE_ENV[@]}" "$IMAGE"

run_container "$PREFIX-noshell-app" --network "$NET" "${PUBLISH[@]}" "$NOSHELL_IMAGE"
run_container "$PREFIX-noshell-side" --pid="container:$PREFIX-noshell-app" \
    --network "container:$PREFIX-noshell-app" --cap-add SYS_PTRACE "${SIDE_ENV[@]}" "$IMAGE"

# A deployment of a product with no relational storage: an ordinary application
# container beside a sidecar configured with no database and no allowlist.
run_container "$PREFIX-nodb-app" --network "$NET" "${PUBLISH[@]}" "$APP_IMAGE"
mapfile -t NODB_ENV < <(sidecar_env_nodb release-nodb-uuid)
run_container "$PREFIX-nodb-side" --pid="container:$PREFIX-nodb-app" \
    --network "container:$PREFIX-nodb-app" "${NODB_ENV[@]}" "$IMAGE"

for owner in "$PREFIX-app" "$PREFIX-lone" "$PREFIX-noshell-app" "$PREFIX-nodb-app"; do
    wait_for_port "$owner" || { echo "sidecar on $owner never opened its port" >&2; docker logs "${owner/-app/-side}" 2>&1 | tail -20; exit 1; }
done

# --- 1. image contents -----------------------------------------------------
group "image: contents and pinning"

out=$(docker run --rm --entrypoint sh "$IMAGE" -c 'psql --version; pg_dump --version')
expect_contains "psql is PostgreSQL 18" "psql (PostgreSQL) 18." "$out"
expect_contains "pg_dump is PostgreSQL 18" "pg_dump (PostgreSQL) 18." "$out"

out=$(docker run --rm --entrypoint sh "$IMAGE" -c '
    find / -xdev \( -name "ssh_host_*" -o -name "authorized_keys" -o -name "id_rsa*" -o -name "id_ed25519*" \) -print 2>/dev/null
    grep -E "^root:[^*!:]" /etc/shadow 2>/dev/null && echo ROOT_HAS_PASSWORD
    echo SCAN_DONE')
expect_eq "no key, authorized_keys or password is baked into the image" "SCAN_DONE" "$out"

# --- 2. startup validation -------------------------------------------------
group "startup: configuration is validated before the server starts"

start_with() {
    docker run --rm --entrypoint /usr/local/bin/freepod-sshd "$@" "$IMAGE" 2>&1
}
good_key=$(cat "$WORK/id.pub")
base=(--env "FREEPOD_RELEASE_ID=r" --env "FREEPOD_LOGIN_USER=$LOGIN_USER"
      --env "PGHOST=h" --env PGPORT=5432
      --env PGUSER=u --env PGPASSWORD=p --env PGDATABASE=d)

out=$(start_with "${base[@]}" --env "FREEPOD_PERMIT_OPEN=h:1"); rc=$?
expect_nonzero "missing trusted key aborts startup" "$rc"
expect_contains "the message names the missing input" "FREEPOD_AUTHORIZED_KEYS" "$out"

out=$(start_with "${base[@]}" --env "FREEPOD_PERMIT_OPEN=h:1" --env "FREEPOD_AUTHORIZED_KEYS=not-a-key"); rc=$?
expect_nonzero "unparseable trusted key aborts startup" "$rc"
expect_contains "the message names the unusable key" "FREEPOD_AUTHORIZED_KEYS" "$out"

for malformed in "pooler" "pooler:*" "pooler:not-a-port" "pooler:99999"; do
    out=$(start_with "${base[@]}" --env "FREEPOD_AUTHORIZED_KEYS=$good_key" --env "FREEPOD_PERMIT_OPEN=$malformed"); rc=$?
    expect_nonzero "malformed allowlist entry '$malformed' aborts startup" "$rc"
    expect_contains "the message names entry '$malformed'" "FREEPOD_PERMIT_OPEN" "$out"
done

out=$(docker run --rm --entrypoint /usr/local/bin/freepod-sshd \
    --env "PGHOST=h" --env PGPORT=5432 --env PGUSER=u --env PGPASSWORD=p --env PGDATABASE=d \
    --env "FREEPOD_LOGIN_USER=$LOGIN_USER" \
    --env "FREEPOD_AUTHORIZED_KEYS=$good_key" --env "FREEPOD_PERMIT_OPEN=h:1" "$IMAGE" 2>&1); rc=$?
expect_nonzero "missing release identity aborts startup" "$rc"
expect_contains "the message names the release identity" "FREEPOD_RELEASE_ID" "$out"

# The edge authenticates the upstream leg as the deployment name, so a sidecar
# with no such account refuses every connection with "Invalid user" -- a refusal
# that looks like an authorization problem from the client end.
out=$(docker run --rm --entrypoint /usr/local/bin/freepod-sshd \
    --env "FREEPOD_RELEASE_ID=r" \
    --env "PGHOST=h" --env PGPORT=5432 --env PGUSER=u --env PGPASSWORD=p --env PGDATABASE=d \
    --env "FREEPOD_AUTHORIZED_KEYS=$good_key" --env "FREEPOD_PERMIT_OPEN=h:1" "$IMAGE" 2>&1); rc=$?
expect_nonzero "missing login account aborts startup" "$rc"
expect_contains "the message names the login account" "FREEPOD_LOGIN_USER" "$out"

out=$(start_with --env "FREEPOD_RELEASE_ID=r" \
    --env "PGHOST=h" --env PGPORT=5432 --env PGUSER=u --env PGPASSWORD=p --env PGDATABASE=d \
    --env "FREEPOD_LOGIN_USER=Not A User" \
    --env "FREEPOD_AUTHORIZED_KEYS=$good_key" --env "FREEPOD_PERMIT_OPEN=h:1"); rc=$?
expect_nonzero "malformed login account aborts startup" "$rc"
expect_contains "the message names the bad account" "FREEPOD_LOGIN_USER" "$out"

# A partial database configuration is not an absent one: it means the projection
# that should have supplied it is broken, and a container that started anyway
# would surface that as a connection error inside psql, at the moment someone
# needed the database and furthest from the cause.
out=$(start_with --env "FREEPOD_RELEASE_ID=r" --env "FREEPOD_LOGIN_USER=$LOGIN_USER" --env PGPORT=5432 --env PGUSER=u \
    --env PGPASSWORD=p --env PGDATABASE=d \
    --env "FREEPOD_AUTHORIZED_KEYS=$good_key" --env "FREEPOD_PERMIT_OPEN=h:1"); rc=$?
expect_nonzero "an incomplete database configuration aborts startup" "$rc"
expect_contains "the message names the missing database input" "PGHOST" "$out"
expect_contains "the message names what was supplied" "PGPORT" "$out"

# --- 3. rendered server configuration --------------------------------------
group "server: rendered configuration"

config=$(docker exec "$PREFIX-side" cat /etc/ssh/sshd_config)
expect_contains "listens on the platform sidecar port"   "Port 2222"                     "$config"
expect_contains "password authentication is off"         "PasswordAuthentication no"     "$config"
expect_contains "keyboard-interactive is off"            "KbdInteractiveAuthentication no" "$config"
expect_contains "public key is the only method"          "AuthenticationMethods publickey" "$config"
expect_contains "root password login is refused"         "PermitRootLogin prohibit-password" "$config"
expect_contains "forwarding is local only"               "AllowTcpForwarding local"      "$config"
expect_contains "agent forwarding is off"                "AllowAgentForwarding no"       "$config"
expect_contains "gateway ports are off"                  "GatewayPorts no"               "$config"
expect_contains "X11 forwarding is off"                  "X11Forwarding no"              "$config"
expect_contains "the dispatcher is the forced command"   "ForceCommand /usr/local/bin/freepod-dispatch" "$config"
expect_contains "the allowlist is rendered"              "PermitOpen $PREFIX-allowed:8080" "$config"
# Chroot is incompatible with the forwarding this profile exists to provide.
expect_missing  "no session is chrooted"                 "ChrootDirectory"               "$config"

# --- 4. host keys ----------------------------------------------------------
group "server: host keys"

a=$(docker exec "$PREFIX-side" cat /etc/ssh/ssh_host_ed25519_key.pub)
b=$(docker exec "$PREFIX-lone" cat /etc/ssh/ssh_host_ed25519_key.pub)
[[ $a != "$b" && -n $a ]] && ok "two containers present different host keys" \
    || bad "two containers present different host keys" "both presented '$a'"
out=$(docker exec "$PREFIX-side" sh -c 'ls /etc/ssh/ssh_host_* | tr "\n" " "')
expect_missing "no RSA host key is generated" "ssh_host_rsa" "$out"

run_container "$PREFIX-timing" --network "$NET" "${PUBLISH[@]}" "${SIDE_ENV[@]}" "$IMAGE"
started=$SECONDS
if wait_for_port "$PREFIX-timing"; then
    elapsed=$((SECONDS - started))
    (( elapsed <= 10 )) && ok "the port opens promptly (${elapsed}s)" \
        || bad "the port opens promptly" "took ${elapsed}s"
else
    bad "the port opens promptly" "the port never opened"
fi
docker rm -f "$PREFIX-timing" >/dev/null

# --- 5. authentication -----------------------------------------------------
group "authentication"

read -r _lu_host _lu_port <<< "$(endpoint_of "$PREFIX-app")"
out=$(ssh -n "${SSH_OPTS[@]}" -i "$WORK/id" -p "$_lu_port" \
    "$LOGIN_USER@$_lu_host" true 2>&1); rc=$?
expect_zero "the deployment-name account authenticates (the edge logs in as it)" "$rc"

out=$(ssh_to "$PREFIX-app" true 2>&1); rc=$?
expect_zero "the supplied key authenticates" "$rc"

read -r host port <<< "$(endpoint_of "$PREFIX-app")"
out=$(ssh -n "${SSH_OPTS[@]}" -i "$WORK/intruder" -p "$port" "root@$host" true 2>&1); rc=$?
expect_nonzero "an unknown key is refused" "$rc"
expect_contains "the refusal names publickey" "publickey" "$out"

out=$(ssh -n -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
    -o ConnectTimeout=10 -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive \
    -o NumberOfPasswordPrompts=1 -p "$port" "root@$host" true 2>&1 </dev/null); rc=$?
expect_nonzero "password authentication is refused" "$rc"
expect_missing "no password prompt is offered" "password:" "$out"

# --- 6. dispatcher: where a session lands ----------------------------------
group "dispatcher: routing"

expect_eq "a shell session reads the application's filesystem" \
    "application-container" "$(ssh_to "$PREFIX-app" 'cat /etc/app-marker' 2>/dev/null)"
expect_eq "a shell session carries the application's environment" \
    "from-the-application" "$(ssh_to "$PREFIX-app" 'echo $APP_ONLY_VAR' 2>/dev/null)"
expect_eq "a shell session starts in the application's working directory" \
    "/app" "$(ssh_to "$PREFIX-app" 'pwd' 2>/dev/null)"
ssh_to "$PREFIX-app" 'test -d /usr/lib/postgresql' >/dev/null 2>&1
expect_nonzero "the sidecar's own filesystem is not what the session sees" "$?"
docker exec "$PREFIX-side" test -d /usr/lib/postgresql
expect_zero "that path does exist in the sidecar, so the test means something" "$?"
expect_eq "a pipeline is interpreted by the application's shell" \
    "application-container" "$(ssh_to "$PREFIX-app" 'cat /etc/app-marker | tr -d "\n"' 2>/dev/null)"
ssh_to "$PREFIX-app" 'exit 7' >/dev/null 2>&1
expect_eq "the remote exit status is the command's own" "7" "$?"

out=$(ssh_to "$PREFIX-app" 'psql -Atc "select current_database()"' 2>&1)
expect_eq "an allowlisted tool runs in the sidecar and reaches the database" "appdb" "$out"
out=$(ssh_to "$PREFIX-app" 'pg_dump --version' 2>&1)
expect_contains "the dump tool runs in the sidecar" "pg_dump (PostgreSQL) 18." "$out"

# Membership is decided on the command, never on arguments a client controls.
out=$(ssh_to "$PREFIX-app" '/bin/echo psql pg_dump' 2>&1)
expect_eq "arguments resembling an allowlisted tool do not make one" "psql pg_dump" "$out"
out=$(ssh_to "$PREFIX-app" 'cat /etc/app-marker psql' 2>&1)
expect_contains "an allowlisted name in an argument stays in the application" "application-container" "$out"

# --- 7. dispatcher: identification -----------------------------------------
group "dispatcher: identifying the application container"

# The harness has no pod infrastructure process, so one is supplied rather than
# the exclusion being inferred from a passing shell.
run_container "$PREFIX-pause" --pid="container:$PREFIX-app" "$APP_IMAGE" /bin/pause infinity
sleep 1
expect_eq "an infrastructure-style cgroup is excluded, not counted" \
    "application-container" "$(ssh_to "$PREFIX-app" 'cat /etc/app-marker' 2>/dev/null)"

run_container "$PREFIX-extra" --pid="container:$PREFIX-app" "$APP_IMAGE"
sleep 1
out=$(ssh_to "$PREFIX-app" 'cat /etc/app-marker' 2>&1); rc=$?
expect_nonzero "a second candidate container is refused, not guessed" "$rc"
expect_contains "the refusal names the ambiguity" "more than one" "$out"
docker rm -f "$PREFIX-extra" "$PREFIX-pause" >/dev/null
sleep 1

out=$(ssh_to "$PREFIX-lone" 'cat /etc/app-marker' 2>&1); rc=$?
expect_nonzero "no application process is reported, not guessed" "$rc"
expect_contains "the report names the likely cause" "process namespace" "$out"

# --- 8. dispatcher: an application container that cannot host the session ---
group "dispatcher: an image that cannot host the session"

out=$(ssh_to "$PREFIX-noshell-app" 2>&1); rc=$?
expect_nonzero "a shell-less application image fails the session" "$rc"
expect_contains "the failure names the cause" "provides no shell" "$out"
expect_missing "no raw execution failure reaches the user" "No such file or directory" "$out"
expect_missing "the session is not opened in the sidecar instead" "postgresql" \
    "$(ssh_to "$PREFIX-noshell-app" 'ls -d /usr/lib/postgresql' 2>&1)"

out=$(ssh_to "$PREFIX-app" 'definitely-not-a-command' 2>&1); rc=$?
expect_eq "a command absent from the application container exits 127" "127" "$rc"
expect_contains "the failure names the command" "definitely-not-a-command" "$out"

# --- 9. dispatcher: the command is never re-interpreted --------------------
group "dispatcher: the requested command is data"

marker=/tmp/dispatcher-must-not-create-this
docker exec "$PREFIX-side" rm -f "$marker" >/dev/null 2>&1
ssh_to "$PREFIX-app" "true; touch $marker" >/dev/null 2>&1
out=$(docker exec "$PREFIX-side" sh -c "ls $marker 2>&1")
expect_contains "a separator does not run a second command in the sidecar" "No such file" "$out"
out=$(docker exec "$PREFIX-app" sh -c "ls $marker 2>&1")
expect_contains "it ran in the application container instead" "$marker" "$out"

docker exec "$PREFIX-side" rm -f "$marker" >/dev/null 2>&1
ssh_to "$PREFIX-app" "psql -Atc 'select 1' > /dev/null; touch $marker" >/dev/null 2>&1
out=$(docker exec "$PREFIX-side" sh -c "ls $marker 2>&1")
expect_contains "an allowlisted tool's session runs in the sidecar's shell as one string" "$marker" "$out"

for hostile in '$(touch /tmp/substituted)' '`touch /tmp/backticked`' '${IFS}touch${IFS}/tmp/expanded'; do
    docker exec "$PREFIX-side" sh -c 'rm -f /tmp/substituted /tmp/backticked /tmp/expanded' >/dev/null 2>&1
    ssh_to "$PREFIX-app" "echo $hostile" >/dev/null 2>&1
    # Count the files, not the error text: an expansion that fired would leave
    # one behind in the sidecar, which is the only observable that matters.
    out=$(docker exec "$PREFIX-side" sh -c 'ls -d /tmp/substituted /tmp/backticked /tmp/expanded 2>/dev/null | wc -l')
    expect_eq "the dispatcher does not expand '$hostile'" "0" "$out"
done

# --- 10. forwarding --------------------------------------------------------
group "forwarding"

forward_and_get() {
    local owner=$1 dest=$2 logfile=$3 lport
    lport=$(( (RANDOM % 20000) + 20000 ))
    local host port; read -r host port <<< "$(endpoint_of "$owner")"
    ssh -n "${SSH_OPTS[@]}" -o LogLevel=INFO -i "$WORK/id" -p "$port" -N -f -o ExitOnForwardFailure=yes \
        -o ControlMaster=no -L "127.0.0.1:$lport:$dest" "root@$host" 2>"$logfile"
    local rc=$?
    if (( rc != 0 )); then echo ""; return "$rc"; fi
    sleep 0.5
    http_get 127.0.0.1 "$lport" 2>>"$logfile"
    pkill -f "127.0.0.1:$lport:$dest" >/dev/null 2>&1
}

out=$(forward_and_get "$PREFIX-app" "$PREFIX-allowed:8080" "$WORK/fwd-ok.log")
expect_contains "a permitted destination carries traffic" "forward-target-allowed" "$out"
# The forward is opened by a process that would inherit a chroot; that it
# resolved a hostname at all is the measurable form of "sessions are not
# chrooted" (D3).
expect_missing "the forward resolved its target by name" "unknown host" "$(cat "$WORK/fwd-ok.log")"

out=$(forward_and_get "$PREFIX-app" "$PREFIX-denied:8080" "$WORK/fwd-no.log")
expect_missing "an unlisted destination carries no traffic" "forward-target-denied" "$out"
# The client only ever sees a connection reset, so the refusal is asserted
# where it is actually stated: the server's own log.
expect_contains "the server refuses the channel" "but the request was denied" \
    "$(docker logs "$PREFIX-side" 2>&1 | tail -20)"

read -r host port <<< "$(endpoint_of "$PREFIX-app")"
ssh -n "${SSH_OPTS[@]}" -i "$WORK/id" -p "$port" -N -f -o ExitOnForwardFailure=yes \
    -R "127.0.0.1:0:127.0.0.1:8080" "root@$host" 2>"$WORK/remote.log"
expect_nonzero "remote forwarding is refused" "$?"

out=$(ssh_to "$PREFIX-app" -A 'echo "sock=[$SSH_AUTH_SOCK]"' 2>/dev/null)
expect_eq "agent forwarding is unavailable in the session" "sock=[]" "$out"

# Forwarding opens no session, so the dispatcher is not involved in it and
# cannot prevent it -- shown on the sidecar whose dispatcher fails every time.
out=$(ssh_to "$PREFIX-lone" true 2>&1); rc=$?
expect_nonzero "the dispatcher fails for a session on this sidecar" "$rc"
out=$(forward_and_get "$PREFIX-lone" "$PREFIX-allowed:8080" "$WORK/fwd-lone.log")
expect_contains "forwarding is unaffected by a dispatcher that would fail" "forward-target-allowed" "$out"

# --- 11. the toolbox does not depend on the application --------------------
group "database toolbox"

out=$(ssh_to "$PREFIX-lone" 'psql -Atc "select current_database()"' 2>&1)
expect_eq "the toolbox works with no application container at all" "appdb" "$out"
ssh_to "$PREFIX-lone" 'psql' </dev/null >/dev/null 2>&1
expect_zero "the client invoked with no arguments connects to the deployment's database" "$?"

# --- 12. banner ------------------------------------------------------------
group "banner"

out=$(ssh_to "$PREFIX-app" -tt 'true' 2>&1 </dev/null | tr -d '\r')
expect_contains "an interactive session reports its release" "freepod: release release-7-uuid" "$out"
# The identity is the configured value, not the pod's or container's name.
expect_missing "the identity is not derived from the container name" "$PREFIX-app" "$out"

expect_eq "no banner reaches standard output" "BODY" "$(ssh_to "$PREFIX-app" 'echo BODY' 2>/dev/null)"

head -c 200000 /dev/urandom > "$WORK/payload.bin"
scp "${SSH_OPTS[@]}" -i "$WORK/id" -P "$port" "$WORK/payload.bin" "root@$host:/tmp/payload.bin" >/dev/null 2>&1
rc=$?
expect_zero "a file copy over the session succeeds" "$rc"
if (( rc == 0 )); then
    expect_eq "the copy is byte-identical and lands in the application container" \
        "$(sha256sum < "$WORK/payload.bin" | cut -d' ' -f1)" \
        "$(docker exec "$PREFIX-app" sha256sum /tmp/payload.bin 2>/dev/null | cut -d' ' -f1)"
    out=$(docker exec "$PREFIX-side" sh -c 'ls /tmp/payload.bin 2>&1')
    expect_contains "the copy did not land in the sidecar" "No such file" "$out"
fi

ssh_to "$PREFIX-app" 'psql -Atc "create table if not exists t (id int); insert into t values (1)"' >/dev/null 2>&1
ssh_to "$PREFIX-app" 'pg_dump' > "$WORK/dump.sql" 2>/dev/null
expect_missing "a streamed dump carries no banner text" "freepod:" "$(cat "$WORK/dump.sql")"
expect_contains "the dump is a real dump" "CREATE TABLE public.t" "$(cat "$WORK/dump.sql")"

# The way back: a dump restored by feeding it to the client's standard input,
# which is what a client offering no upload of its own has to rely on. `ssh_to`
# passes -n, so this case calls ssh directly -- stdin is the whole point of it.
ssh_to "$PREFIX-app" 'psql -Atc "drop table t"' >/dev/null 2>&1
read -r host port <<< "$(endpoint_of "$PREFIX-app")"
ssh "${SSH_OPTS[@]}" -i "$WORK/id" -p "$port" "root@$host" psql < "$WORK/dump.sql" >/dev/null 2>&1
expect_eq "a dump restores over standard input" "1" \
    "$(ssh_to "$PREFIX-app" 'psql -Atc "select count(*) from t"' 2>/dev/null)"

# The custom format needs the other tool and an explicit target database, which
# is why the connection details are staged as PG* rather than composed into a
# URL: the name is already in the session's environment, so a restore does not
# have to be told what it is restoring into.
ssh_to "$PREFIX-app" 'pg_dump -Fc' > "$WORK/dump.pgc" 2>/dev/null
ssh_to "$PREFIX-app" 'psql -Atc "drop table t"' >/dev/null 2>&1
ssh "${SSH_OPTS[@]}" -i "$WORK/id" -p "$port" "root@$host" 'pg_restore -d "$PGDATABASE"' \
    < "$WORK/dump.pgc" >/dev/null 2>&1
expect_eq "a custom-format dump restores with pg_restore" "1" \
    "$(ssh_to "$PREFIX-app" 'psql -Atc "select count(*) from t"' 2>/dev/null)"

# --- 13. a product with no database ----------------------------------------
# The toolbox and the forward are facilities this profile offers, not
# preconditions it imposes, so their absence must cost only themselves. Every
# other session path is the same server as above.
group "no database: the rest of the session is unchanged"

config=$(docker exec "$PREFIX-nodb-side" cat /etc/ssh/sshd_config)
# An empty allowlist must be written as `none`, never left out: sshd's default
# is to permit forwarding to anywhere, so silence would turn "nothing to allow"
# into "allow everything", from a host with tenant egress to the internet.
expect_contains "an empty allowlist is written as a refusal" "PermitOpen none" "$config"
expect_contains "the startup log states there is no database" "database none" \
    "$(docker logs "$PREFIX-nodb-side" 2>&1)"

expect_eq "a shell session still reads the application's filesystem" \
    "application-container" "$(ssh_to "$PREFIX-nodb-app" 'cat /etc/app-marker' 2>/dev/null)"
expect_eq "a shell session still starts in the application's working directory" \
    "/app" "$(ssh_to "$PREFIX-nodb-app" 'pwd' 2>/dev/null)"

out=$(ssh_to "$PREFIX-nodb-app" 'psql -Atc "select 1"' 2>&1); rc=$?
expect_nonzero "a database tool is declined rather than left to fail" "$rc"
expect_contains "the refusal names the cause" "no database" "$out"
expect_missing "no bare connection failure reaches the user instead" "could not connect" "$out"

out=$(forward_and_get "$PREFIX-nodb-app" "$PREFIX-allowed:8080" "$WORK/fwd-nodb.log")
expect_missing "every forward is refused" "forward-target-allowed" "$out"

# The staged session environment is the only path by which a database
# credential could reach a session, so its absence is asserted, not assumed.
out=$(docker exec "$PREFIX-nodb-side" sh -c 'tr "\0" "\n" < /etc/freepod/session-env')
expect_missing "no database credential is staged for the session" "PGPASSWORD" "$out"
expect_contains "the release identity is still staged" "release-nodb-uuid" "$out"

# --- summary ---------------------------------------------------------------
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
if (( FAIL )); then
    printf 'failed:\n'; printf '  - %s\n' "${FAILED_NAMES[@]}"
    exit 1
fi
