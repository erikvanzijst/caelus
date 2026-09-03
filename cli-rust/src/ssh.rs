//! SSH connection assembly for `shell`, `db shell` and `db proxy`.
//!
//! The client does not implement SSH; it drives the system `ssh`. This module
//! is the assembly those commands share: it names the one key to offer, pins
//! the edge's host key to the value the platform publishes, and builds the
//! argument list. It knows nothing about what the connection is *for* — a
//! shell, a forward, a database session — that is the caller's argument,
//! appended last. Mirrors `ssh.py`.

use std::path::{Path, PathBuf};

use serde_json::Value;

use crate::config::{config_dir, ensure_config_dir};
use crate::errors::{freepod, host_key_mismatch, Error, Result};

/// The one line of ssh's stderr that identifies a host-key mismatch.
const HOST_KEY_MISMATCH: &str = "host key verification failed";

/// The one phrase ssh's stderr carries when the far end declines a forward.
/// It is the refusal that reads like an authorization failure in practice:
/// the key was accepted, the channel opened, and the destination was not
/// permitted.
const FORWARD_REFUSED: &str = "administratively prohibited";

/// The client's own known_hosts, beside the token cache.
///
/// Never the user's `~/.ssh/known_hosts`: a mismatch must be this client's
/// failure to report, not a modification of a file the user curates, and a
/// user who keeps their own entry for the edge should not have it overridden.
pub fn known_hosts_path() -> PathBuf {
    config_dir().join("known_hosts")
}

/// The system `ssh`, or a named-prerequisite error naming what to install.
///
/// A missing `ssh` is a prerequisite, not a fault of this client, so it is
/// reported by name with the fix rather than surfacing as an unhandled spawn
/// failure deep in a subprocess call.
pub fn require_ssh() -> Result<String> {
    let path = std::env::var_os("PATH").unwrap_or_default();
    for dir in std::env::split_paths(&path) {
        if dir.as_os_str().is_empty() {
            continue;
        }
        let candidate = dir.join("ssh");
        if candidate.is_file() && is_executable(&candidate) {
            return Ok(candidate.to_string_lossy().into_owned());
        }
    }
    Err(freepod(
        "the system `ssh` executable is required but was not found on your \
         PATH. Install OpenSSH — for example `apt-get install openssh-client` \
         or `brew install openssh` — and try again.",
    ))
}

#[cfg(unix)]
fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    path.metadata()
        .map(|m| m.permissions().mode() & 0o111 != 0)
        .unwrap_or(false)
}

#[cfg(not(unix))]
fn is_executable(path: &Path) -> bool {
    path.exists()
}

/// The known_hosts spelling of one endpoint: port-qualified unless it is 22.
fn host_part(host: &str, port: u16) -> String {
    if port == 22 {
        host.to_string()
    } else {
        format!("[{host}]:{port}")
    }
}

/// One OpenSSH known_hosts line for a published host key.
fn known_hosts_entry(host: &str, port: u16, key_type: &str, base64: &str) -> String {
    format!("{} {} {}", host_part(host, port), key_type, base64)
}

/// Record the published host key in the client's own known_hosts.
///
/// Upserts the line for this endpoint — replacing a stale entry for the same
/// host:port, leaving every other line untouched — and writes it owner-only in
/// the 0700 config directory. The line is the value the platform published, so
/// a later `StrictHostKeyChecking` connection accepts the real edge and refuses
/// anything else.
pub fn seed_known_hosts(host: &str, port: u16, key_type: &str, base64: &str) -> Result<PathBuf> {
    let target = host_part(host, port);
    let path = known_hosts_path();
    let mut lines: Vec<String> = Vec::new();
    if path.is_file() {
        let text = std::fs::read_to_string(&path)
            .map_err(|e| freepod(format!("cannot read {}: {e}", path.display())))?;
        for line in text.lines() {
            if line.trim().is_empty() {
                continue;
            }
            if line.split_whitespace().next() == Some(target.as_str()) {
                // A stale entry for this endpoint is replaced, not accumulated.
                continue;
            }
            lines.push(line.to_string());
        }
    }
    lines.push(known_hosts_entry(host, port, key_type, base64));

    ensure_config_dir();
    let pid = std::process::id();
    let temporary = path.with_file_name(format!("known_hosts.{pid}.tmp"));
    let text = format!("{}\n", lines.join("\n"));
    match std::fs::write(&temporary, text.as_bytes()) {
        Ok(()) => {
            set_mode(&temporary, 0o600);
            std::fs::rename(&temporary, &path).map_err(|e| {
                let _ = std::fs::remove_file(&temporary);
                freepod(format!("cannot write {}: {e}", path.display()))
            })?;
            set_mode(&path, 0o600);
        }
        Err(e) => {
            let _ = std::fs::remove_file(&temporary);
            return Err(freepod(format!("cannot write {}: {e}", path.display())));
        }
    }
    Ok(path)
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) {
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(mode));
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) {}

/// Verify the edge's published host key and pin it in the client's store.
///
/// Returns the `(host, port, known_hosts)` that `build_args` needs. The host
/// key is a per-environment fact the platform already knows, so the one
/// connection worth attacking — the first, which would otherwise trust whatever
/// answers — is checked against it rather than guessed at. An environment that
/// has not configured a key reports an empty `host_key`; that is refused as
/// "cannot verify", never treated as permission to trust on first use.
pub fn pin_edge(edge: &Value) -> Result<(String, u16, PathBuf)> {
    let host = edge
        .get("host")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .ok_or_else(|| {
            freepod("the platform reported no SSH edge address; please report this.")
        })?
        .to_string();
    let port = edge
        .get("port")
        .and_then(|v| v.as_u64())
        .filter(|p| *p <= u16::MAX as u64)
        .ok_or_else(|| {
            freepod("the platform reported no SSH edge address; please report this.")
        })? as u16;
    let host_key = edge.get("host_key").and_then(|v| v.as_object());
    let Some(host_key) = host_key.filter(|o| !o.is_empty()) else {
        return Err(freepod(
            "this environment has not published an SSH host key, so the edge \
             cannot be verified. No connection was attempted. Please report \
             this — the platform should know the answer.",
        ));
    };
    // The platform publishes the edge's single host key, keyed by OpenSSH type.
    let (key_type, base64) = host_key.iter().next().unwrap();
    let base64 = base64.as_str().unwrap_or("").to_string();
    let known_hosts = seed_known_hosts(&host, port, key_type, &base64)?;
    Ok((host, port, known_hosts))
}

/// The file to hand to `-i`: the private half, where there is one on disk.
///
/// The record is keyed by the public key, and a key held only in an agent or
/// on a hardware token has no private file at all — for those, the public key
/// is what selects the identity. But a file-based key must be offered by its
/// private half: ssh refuses a world-readable public key as an identity, and a
/// public key cannot sign. Where the private half sits beside the public one
/// (the layout `freepod key add` writes), it is the one that authenticates.
pub fn identity_file(key_path: &Path) -> PathBuf {
    if key_path.extension().is_some_and(|ext| ext == "pub") {
        let private = key_path.with_extension("");
        if private.is_file() {
            return private;
        }
    }
    key_path.to_path_buf()
}

/// The pieces of one connection to the edge, in the order `build_args` needs
/// them. `command` is what the session runs once it lands; `local_forward` is
/// the `-L` destination for a tunnel that runs no session.
pub struct Connection {
    pub user: String,
    pub host: String,
    pub port: u16,
    pub key_path: PathBuf,
    pub known_hosts: PathBuf,
    pub command: Option<Vec<String>>,
    pub local_forward: Option<String>,
    pub tty: bool,
}

/// The argv for one connection to the edge.
///
/// Exactly one identity is offered, and the edge's host key is pinned to the
/// value the platform published. The options that make a host-key mismatch a
/// refusal rather than a prompt sit beside their reason, because each looks
/// like belt-and-braces until the day someone removes one.
pub fn build_args(c: &Connection) -> Vec<String> {
    let mut args = vec![
        "ssh".to_string(),
        "-p".to_string(),
        c.port.to_string(),
        // One identity, and only that one. The edge answers *every* offered key
        // with a partial success, so a client that offers several — which a
        // populated agent does by default — exhausts the server's authentication
        // budget and is refused before it reaches the right key.
        "-o".to_string(),
        "IdentitiesOnly=yes".to_string(),
        "-i".to_string(),
        identity_file(&c.key_path).to_string_lossy().into_owned(),
        // Pin the edge to the key the platform published, in a store the user
        // does not curate. StrictHostKeyChecking means a mismatch is a refusal,
        // never a prompt, and never a key recorded on first use.
        "-o".to_string(),
        format!("UserKnownHostsFile={}", c.known_hosts.display()),
        "-o".to_string(),
        "StrictHostKeyChecking=yes".to_string(),
    ];
    if c.tty {
        // Force a remote tty. The sidecar runs under a ForceCommand, which does
        // not allocate a pseudo-terminal on its own, so an interactive session
        // comes up without one — and a database client that reads no terminal
        // sees no prompt — unless we ask for it here.
        args.push("-tt".to_string());
    }
    args.push(format!("{}@{}", c.user, c.host));
    if let Some(forward) = &c.local_forward {
        // -N: no remote command; the forward is the whole point of the session.
        args.push("-N".to_string());
        args.push("-L".to_string());
        args.push(forward.clone());
    }
    if let Some(command) = &c.command {
        args.extend(command.iter().cloned());
    }
    args
}

/// Whether ssh's failure was a host-key mismatch, not an auth or network one.
pub fn is_host_key_mismatch(stderr: &[u8]) -> bool {
    String::from_utf8_lossy(stderr)
        .to_lowercase()
        .contains(HOST_KEY_MISMATCH)
}

/// Whether ssh's failure was a refused forward, not an auth or network one.
///
/// A forward is refused *after* authentication, so the two failures are
/// distinguishable in ssh's own output: an authentication refusal says
/// "Permission denied", a forward refusal says the destination was
/// administratively prohibited. Naming the cause the client can support —
/// rather than guessing — is what keeps the two from blurring into one.
pub fn is_forward_refused(stderr: &[u8]) -> bool {
    String::from_utf8_lossy(stderr)
        .to_lowercase()
        .contains(FORWARD_REFUSED)
}

/// Run a session on the user's own terminal; return its exit code.
///
/// An interactive session or a single remote command alike: both own the
/// foreground, so nothing is captured. The user's own stdin, stdout and stderr
/// are the session's, which is what lets a command be redirected or piped on
/// either side, and a host-key mismatch reach the user in real time. The exit
/// code is handed back for the caller to propagate; there is no captured
/// stream to re-classify here — whatever ssh said, the user read.
pub fn run_interactive(argv: &[String]) -> Result<i32> {
    let status = std::process::Command::new(&argv[0])
        .args(&argv[1..])
        .status()
        .map_err(|e| freepod(format!("cannot run ssh: {e}")))?;
    #[cfg(unix)]
    {
        use std::os::unix::process::ExitStatusExt;
        // Terminated by a signal: report it, the way the shell would.
        Ok(status.code().unwrap_or_else(|| 128 + status.signal().unwrap_or(1)))
    }
    #[cfg(not(unix))]
    Ok(status.code().unwrap_or(1))
}

/// The error a captured host-key mismatch raises, by name.
pub fn mismatch_error() -> Error {
    host_key_mismatch(
        "the SSH edge presented a host key that does not match the one the \
         platform publishes. The connection was refused and nothing was \
         recorded. If you did not change the edge's host key, report this — \
         it means something else is answering where the edge should be.",
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testutil::ENV_LOCK;
    use std::ffi::OsString;

    /// Repoint `XDG_CONFIG_HOME` at a throwaway directory so `seed_known_hosts`
    /// and `pin_edge` write to a store that is not the user's.
    struct IsolatedConfig {
        config: PathBuf,
        _guard: std::sync::MutexGuard<'static, ()>,
    }

    impl IsolatedConfig {
        fn new(tag: &str) -> Self {
            let guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
            let pid = std::process::id();
            let config = std::env::temp_dir().join(format!("freepod-ssh-xdg-{tag}-{pid}"));
            let _ = std::fs::remove_dir_all(&config);
            std::fs::create_dir_all(&config).unwrap();
            std::env::set_var("XDG_CONFIG_HOME", &config);
            Self {
                config,
                _guard: guard,
            }
        }

        fn cleanup(&self) {
            std::env::remove_var("XDG_CONFIG_HOME");
            let _ = std::fs::remove_dir_all(&self.config);
        }

        /// The client's config directory under the isolated root.
        fn dir(&self) -> PathBuf {
            self.config.join("freepod")
        }
    }

    impl Drop for IsolatedConfig {
        fn drop(&mut self) {
            self.cleanup();
        }
    }

    /// Repoint `PATH` at a throwaway directory so `require_ssh` and the
    /// `run_interactive` fakes see only what the test puts there.
    struct IsolatedPath {
        dir: PathBuf,
        original: Option<OsString>,
        _guard: std::sync::MutexGuard<'static, ()>,
    }

    impl IsolatedPath {
        fn new(tag: &str) -> Self {
            let guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
            let original = std::env::var_os("PATH");
            let pid = std::process::id();
            let dir = std::env::temp_dir().join(format!("freepod-ssh-path-{tag}-{pid}"));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).unwrap();
            std::env::set_var("PATH", &dir);
            Self {
                dir,
                original,
                _guard: guard,
            }
        }

        /// A fake `ssh` that records its argv and exits with the given code.
        fn fake_ssh(&self, exit_code: i32) -> PathBuf {
            let path = self.dir.join("ssh");
            std::fs::write(
                &path,
                format!(
                    "#!/bin/bash\nprintf '%s\\n' \"$@\" > {}/argv.txt\nexit {exit_code}\n",
                    self.dir.display()
                ),
            )
            .unwrap();
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let mut perms = std::fs::metadata(&path).unwrap().permissions();
                perms.set_mode(0o755);
                std::fs::set_permissions(&path, perms).unwrap();
            }
            path
        }

        fn cleanup(&self) {
            match &self.original {
                Some(v) => std::env::set_var("PATH", v),
                None => std::env::remove_var("PATH"),
            }
            let _ = std::fs::remove_dir_all(&self.dir);
        }
    }

    impl Drop for IsolatedPath {
        fn drop(&mut self) {
            self.cleanup();
        }
    }

    // --- the ssh prerequisite ---------------------------------------------

    #[test]
    fn require_ssh_returns_the_executable() {
        let path = IsolatedPath::new("require-found");
        let ssh = path.fake_ssh(0);
        assert_eq!(require_ssh().unwrap(), ssh.to_string_lossy());
    }

    #[test]
    fn require_ssh_names_the_prerequisite_when_missing() {
        let _path = IsolatedPath::new("require-missing");
        let err = require_ssh().unwrap_err();
        let msg = err.message();
        assert!(msg.contains("ssh"));
        assert!(msg.to_lowercase().contains("openssh"));
        assert!(msg.contains("PATH"));
    }

    // --- the client's own known_hosts -------------------------------------

    #[test]
    fn known_hosts_lives_beside_the_token_cache() {
        assert_eq!(known_hosts_path().parent().unwrap(), crate::config::config_dir());
        assert_eq!(
            known_hosts_path().parent().unwrap(),
            crate::config::token_cache_path().parent().unwrap()
        );
    }

    #[test]
    fn seed_writes_the_published_key_for_port_22() {
        let cfg = IsolatedConfig::new("seed-22");
        let path = seed_known_hosts("freepod.eu", 22, "ssh-ed25519", "AAAAhostkey").unwrap();
        assert_eq!(
            std::fs::read_to_string(&path).unwrap().lines().collect::<Vec<_>>(),
            vec!["freepod.eu ssh-ed25519 AAAAhostkey"]
        );
        assert_eq!(path, cfg.dir().join("known_hosts"));
    }

    #[test]
    fn seed_qualifies_the_port_when_it_is_not_22() {
        let _cfg = IsolatedConfig::new("seed-port");
        let path = seed_known_hosts("freepod.eu", 2222, "ssh-ed25519", "AAAAhostkey").unwrap();
        assert_eq!(
            std::fs::read_to_string(&path).unwrap().lines().collect::<Vec<_>>(),
            vec!["[freepod.eu]:2222 ssh-ed25519 AAAAhostkey"]
        );
    }

    #[test]
    fn seed_replaces_a_stale_entry_for_the_same_endpoint() {
        let _cfg = IsolatedConfig::new("seed-stale");
        seed_known_hosts("freepod.eu", 22, "ssh-ed25519", "OLDkey").unwrap();
        let path = seed_known_hosts("freepod.eu", 22, "ssh-ed25519", "NEWkey").unwrap();
        assert_eq!(
            std::fs::read_to_string(&path).unwrap().lines().collect::<Vec<_>>(),
            vec!["freepod.eu ssh-ed25519 NEWkey"]
        );
    }

    #[test]
    fn seed_keeps_other_endpoints_intact() {
        let _cfg = IsolatedConfig::new("seed-multi");
        seed_known_hosts("freepod.eu", 22, "ssh-ed25519", "PRODkey").unwrap();
        let path = seed_known_hosts("dev.freepod.eu", 22, "ssh-ed25519", "DEVkey").unwrap();
        let text = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert!(lines.contains(&"freepod.eu ssh-ed25519 PRODkey"));
        assert!(lines.contains(&"dev.freepod.eu ssh-ed25519 DEVkey"));
        assert_eq!(lines.len(), 2);
    }

    #[test]
    #[cfg(unix)]
    fn seed_is_written_owner_only() {
        let _cfg = IsolatedConfig::new("seed-mode");
        let path = seed_known_hosts("freepod.eu", 22, "ssh-ed25519", "AAAAhostkey").unwrap();
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(path.metadata().unwrap().permissions().mode() & 0o777, 0o600);
    }

    // --- pin_edge: verify the published key before connecting --------------

    #[test]
    fn pin_edge_seeds_the_store_and_returns_the_target() {
        let cfg = IsolatedConfig::new("pin-ok");
        let edge = serde_json::json!({"host": "freepod.eu", "port": 22, "host_key": {"ssh-ed25519": "AAAAedge"}});
        let (host, port, store) = pin_edge(&edge).unwrap();
        assert_eq!((host.as_str(), port), ("freepod.eu", 22));
        assert_eq!(
            std::fs::read_to_string(&store).unwrap().lines().collect::<Vec<_>>(),
            vec!["freepod.eu ssh-ed25519 AAAAedge"]
        );
        assert_eq!(store, cfg.dir().join("known_hosts"));
    }

    #[test]
    fn pin_edge_refuses_an_unpublished_key() {
        let _cfg = IsolatedConfig::new("pin-empty");
        let edge = serde_json::json!({"host": "freepod.eu", "port": 22, "host_key": {}});
        let err = pin_edge(&edge).unwrap_err();
        assert!(err.message().contains("cannot be verified"));
    }

    #[test]
    fn pin_edge_refuses_a_missing_address() {
        let _cfg = IsolatedConfig::new("pin-nohost");
        let edge = serde_json::json!({"host": "", "port": 22, "host_key": {"ssh-ed25519": "AAAA"}});
        assert!(pin_edge(&edge).is_err());
    }

    // --- exactly one identity offered -------------------------------------

    fn base() -> Connection {
        Connection {
            user: "myapp".to_string(),
            host: "freepod.eu".to_string(),
            port: 22,
            key_path: PathBuf::from("/keys/id_ed25519.pub"),
            known_hosts: PathBuf::from("/config/known_hosts"),
            command: None,
            local_forward: None,
            tty: false,
        }
    }

    #[test]
    fn offers_exactly_one_identity() {
        let args = build_args(&base());
        assert_eq!(args.iter().filter(|a| **a == "-i").count(), 1);
        let identity = &args[args.iter().position(|a| a == "-i").unwrap() + 1];
        assert_eq!(identity, "/keys/id_ed25519.pub");
        assert!(args.contains(&"IdentitiesOnly=yes".to_string()));
    }

    #[test]
    fn the_identity_is_the_private_half_where_one_exists() {
        let dir = std::env::temp_dir().join(format!("freepod-ssh-id-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let private = dir.join("id_ed25519");
        let pub_path = dir.join("id_ed25519.pub");
        std::fs::write(&private, b"private").unwrap();
        std::fs::write(&pub_path, b"public").unwrap();
        assert_eq!(identity_file(&pub_path), private);
        let mut c = base();
        c.key_path = pub_path.clone();
        let args = build_args(&c);
        assert_eq!(
            &args[args.iter().position(|a| a == "-i").unwrap() + 1],
            &private.to_string_lossy()
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_identity_is_the_public_key_when_no_private_half_exists() {
        assert_eq!(
            identity_file(Path::new("/keys/id_ed25519.pub")),
            PathBuf::from("/keys/id_ed25519.pub")
        );
    }

    #[test]
    fn pins_the_edge_to_the_client_store() {
        let args = build_args(&base());
        assert!(args.contains(&"UserKnownHostsFile=/config/known_hosts".to_string()));
        assert!(args.contains(&"StrictHostKeyChecking=yes".to_string()));
        assert!(!args.iter().any(|a| a.contains(".ssh/known_hosts")));
    }

    #[test]
    fn targets_the_edge_with_the_deployment_as_user() {
        let args = build_args(&base());
        assert!(args.contains(&"myapp@freepod.eu".to_string()));
        let p = args.iter().position(|a| a == "-p").unwrap();
        assert_eq!(args[p + 1], "22");
    }

    #[test]
    fn forward_is_a_no_remote_command_tunnel() {
        let mut c = base();
        c.local_forward = Some("127.0.0.1:5432:caelus-db:5432".to_string());
        let args = build_args(&c);
        assert!(args.contains(&"-N".to_string()));
        let l = args.iter().position(|a| a == "-L").unwrap();
        assert_eq!(args[l + 1], "127.0.0.1:5432:caelus-db:5432");
        assert!(args.contains(&"myapp@freepod.eu".to_string()));
    }

    #[test]
    fn remote_command_is_appended_last() {
        let mut c = base();
        c.command = Some(vec!["psql".to_string(), "-d".to_string(), "app".to_string()]);
        let args = build_args(&c);
        assert_eq!(&args[args.len() - 3..], &["psql", "-d", "app"]);
        assert!(args.contains(&"myapp@freepod.eu".to_string()));
    }

    #[test]
    fn tty_is_requested_only_when_asked() {
        assert!(!build_args(&base()).contains(&"-tt".to_string()));
        let mut c = base();
        c.tty = true;
        assert!(build_args(&c).contains(&"-tt".to_string()));
    }

    #[test]
    fn tty_sits_with_the_options_before_the_target() {
        let mut c = base();
        c.tty = true;
        let args = build_args(&c);
        assert!(
            args.iter().position(|a| a == "-tt").unwrap()
                < args.iter().position(|a| a == "myapp@freepod.eu").unwrap()
        );
    }

    // --- the edge is verified, not trusted --------------------------------

    #[test]
    fn mismatch_is_recognised_from_stderr() {
        assert!(is_host_key_mismatch(b"Host key verification failed."));
        assert!(!is_host_key_mismatch(b"Permission denied (publickey)."));
        assert!(!is_host_key_mismatch(b""));
    }

    #[test]
    fn forward_refusal_is_recognised_from_stderr() {
        assert!(is_forward_refused(
            b"channel 0: open failed: administratively prohibited: administratively prohibited"
        ));
        assert!(!is_forward_refused(b"Permission denied (publickey)."));
        assert!(!is_forward_refused(b""));
    }

    #[test]
    fn run_interactive_returns_the_exit_code() {
        let path = IsolatedPath::new("run-exit");
        let ssh = path.fake_ssh(3);
        let code = run_interactive(&[ssh.to_string_lossy().into_owned(), "x@y".to_string()])
            .unwrap();
        assert_eq!(code, 3);
    }

    #[test]
    fn mismatch_error_names_the_cause() {
        let err = mismatch_error();
        assert!(err.message().contains("does not match"));
        assert_eq!(err.exit_code(), crate::errors::EXIT_ERROR);
    }
}
