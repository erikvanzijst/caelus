#!/bin/bash
# The session dispatcher. sshd runs this as ForceCommand, so it sees the
# requested command in SSH_ORIGINAL_COMMAND and decides where the session
# lands: a shell in the application container, a platform tool in the sidecar,
# or nothing at all. Port forwarding is a `direct-tcpip` channel and opens no
# session, so it never reaches this program (D3).
#
# The requested command is attacker-influenced input arriving at an
# authenticated boundary. This program never evaluates it. Where a command has
# to be interpreted, it is handed to a shell *in the target* as one quoted
# argument -- which is what sshd itself would do, so `ssh host 'ls | wc -l'`
# still behaves as expected, with the application container's shell doing the
# interpreting rather than anything here.
set -uo pipefail

readonly SESSION_ENV=/etc/freepod/session-env
readonly SHELLS=(/bin/bash /bin/sh /bin/ash /busybox/sh)
readonly SFTP_SERVERS=(/usr/lib/openssh/sftp-server /usr/libexec/openssh/sftp-server /usr/lib/ssh/sftp-server)

# Tools that live here and nowhere else. Membership is decided on the command
# itself, never on arguments a client controls.
readonly PLATFORM_COMMANDS=(psql pg_dump pg_dumpall pg_restore pg_isready)

say() { echo "freepod: $*" >&2; }
die() { say "$*"; exit 1; }

# --- configuration ---------------------------------------------------------
# sshd hands a session a sanitized environment, so the container's own
# variables are staged by the entrypoint in /proc/<pid>/environ's NUL-delimited
# form and read back here. NUL delimiting is what makes this safe for values
# holding newlines, quotes or spaces -- nothing is parsed or re-evaluated.
if [[ -r $SESSION_ENV ]]; then
    while IFS= read -r -d '' entry; do
        [[ $entry =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] && export "${entry?}"
    done < "$SESSION_ENV"
fi

# --- banner ----------------------------------------------------------------
# Standard output is a protocol channel for file transfer and dump streams, so
# a banner written there corrupts the transfer and produces a data error far
# from its cause. It goes to standard error, and only when a terminal was
# allocated. The release identity comes from configuration: during a rollout
# two releases' pods both serve and the connection lands on one at random, so a
# developer must be told which one answered (D17).
[[ -t 2 ]] && say "release ${FREEPOD_RELEASE_ID:-unknown}"

# --- routing ---------------------------------------------------------------
command=${SSH_ORIGINAL_COMMAND:-}

# Word splitting on the requested command, with globbing off. This expansion
# yields words and nothing else -- no command substitution, no evaluation --
# which is what makes reading the first token safe.
set -f
# shellcheck disable=SC2086
set -- $command
set +f
verb=${1:-}

for platform_command in "${PLATFORM_COMMANDS[@]}"; do
    if [[ $verb == "$platform_command" ]]; then
        # The tool and its connection details are here, so this runs here. The
        # string still goes to a shell as one argument, so pipes and
        # redirections work the way a remote command should.
        exec /bin/sh -c "$command"
    fi
done

# --- identify the application container ------------------------------------
# Candidates are grouped by cgroup. The dispatcher's own cgroup is excluded,
# and so is the pod's infrastructure process, which is the `pause` binary under
# every CRI. Exactly one cgroup must remain.
#
# Simpler rules are wrong in ways that matter: under Kubernetes with a shared
# process namespace PID 1 is the infrastructure container, while under the
# docker test harness there is no such process and the application *is* PID 1.
# Grouping by cgroup is correct in both, which is what lets the harness prove
# the production behavior rather than an approximation of it.
find_app_pid() {
    local self_cgroup pid cgroup comm
    self_cgroup=$(< /proc/self/cgroup) || return 1

    local -A lowest=()
    for pid in /proc/[0-9]*; do
        pid=${pid#/proc/}
        [[ -r /proc/$pid/cgroup ]] || continue
        cgroup=$(< "/proc/$pid/cgroup") || continue
        [[ $cgroup == "$self_cgroup" ]] && continue
        # Every file under /proc reports a size of zero, so a test for a
        # non-empty cmdline silently excludes everything. The exe link is the
        # honest check: kernel threads and reaped zombies have none.
        [[ -n $(readlink "/proc/$pid/exe" 2>/dev/null) ]] || continue
        comm=$(< "/proc/$pid/comm") || continue
        [[ $comm == pause ]] && continue                  # pod infrastructure
        [[ -z ${lowest[$cgroup]:-} || pid -lt ${lowest[$cgroup]} ]] && lowest[$cgroup]=$pid
    done

    case ${#lowest[@]} in
        0) return 1 ;;
        1) printf '%s\n' "${lowest[@]}" ;;
        *) return 2 ;;
    esac
}

# Only now, once the request is known not to be a platform tool: a developer
# reaches for psql precisely when the application is broken, so the toolbox
# must not depend on an application container being identifiable at all.
app_pid=$(find_app_pid)
case $? in
    1)  die "no application process is visible from the sidecar. The application container is not running, or the pod does not share a process namespace." ;;
    2)  die "more than one candidate application container is visible; refusing to guess which one to enter." ;;
esac
readonly app_pid
readonly app_root=/proc/$app_pid/root

# A subsystem request arrives as its configured command name. Modern scp and
# sftp use it, so it is mapped onto the application container's own
# sftp-server -- the same helper-on-the-remote-side model every file transfer
# tool uses, and the same reason `kubectl cp` needs tar in the target.
if [[ $verb == internal-sftp || $verb == sftp-server ]] && (( $# == 1 )); then
    for candidate in "${SFTP_SERVERS[@]}"; do
        if [[ -x $app_root$candidate ]]; then
            exec chroot "$app_root" "$candidate"
        fi
    done
    die "the application image contains no sftp-server, so file transfer over SFTP is not available. Copy with 'scp -O', with rsync, or over tar, and check that the tool exists in your image."
fi

# --- enter the application container ---------------------------------------
app_shell=""
for candidate in "${SHELLS[@]}"; do
    [[ -x $app_root$candidate ]] && { app_shell=$candidate; break; }
done

if [[ -z $app_shell ]]; then
    # Reported, not crashed, and not redirected somewhere else. `docker exec`
    # and `kubectl exec` fail here too, the image is the user's own, and adding
    # a shell to it is a change they can make. Landing them in the sidecar
    # instead would have them debug a container that is not theirs.
    die "the application image provides no shell (looked for ${SHELLS[*]}), so no session can be opened in it. Add one to the image to use 'freepod shell'."
fi

app_cwd=$(readlink "/proc/$app_pid/cwd" 2>/dev/null) || app_cwd=/

# The application process's own environment, read from the sidecar rather than
# reconstructed. Read NUL-delimited so a value holding a newline -- a private
# key in a deployment var, say -- survives intact.
env_args=()
while IFS= read -r -d '' entry; do
    [[ $entry =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] && env_args+=("$entry")
done < "/proc/$app_pid/environ"
[[ -n ${TERM:-} ]] && env_args+=("TERM=$TERM")

# Fixed script text with everything variable passed as a positional argument,
# so no part of the request is ever interpolated into the program being run.
readonly ENTER='cd "$1" 2>/dev/null || cd /; shift; if [ "$#" -eq 0 ]; then exec "$0" -l; else exec "$0" -c "$1"; fi'

if [[ -z $command ]]; then
    exec env -i "${env_args[@]}" chroot "$app_root" "$app_shell" -c "$ENTER" "$app_shell" "$app_cwd"
else
    exec env -i "${env_args[@]}" chroot "$app_root" "$app_shell" -c "$ENTER" "$app_shell" "$app_cwd" "$command"
fi
