//! `freepod key`: the account's SSH keys, and which one this machine holds.
//!
//! Mirrors `keys.py`. Registration is the one moment the client knows both
//! halves of a pair, so it is where the link between a registered public key
//! and a local file is recorded rather than guessed later. The edge answers
//! every offered key with "partial success", so a client that tries several
//! exhausts `MaxAuthTries` before reaching the right one — it must know which
//! key to offer.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::api::{encode_segment, ApiClient, ApiResponse};
use crate::config::{config_dir, ensure_config_dir};
use crate::errors::{freepod, usage, Error, Result};
use crate::table::{format_time, render, BLANK};

const COLUMNS: [&str; 5] = ["", "FINGERPRINT", "LABEL", "TYPE", "ADDED"];

/// The client-generated key, per machine and shared across environments; which
/// of them it is *registered* on is what the record below keys by environment.
const GENERATED_KEY_NAME: &str = "id_ed25519";

const RECORD_VERSION: u64 = 1;

// --------------------------------------------------------------------------
// Fingerprints
// --------------------------------------------------------------------------

/// `SHA256:...` for one OpenSSH public key line, or None if unreadable.
///
/// The blob decode is strict: a key line whose base64 does not validate has no
/// fingerprint, and the digest is encoded without padding, the way
/// `ssh-keygen -lf` prints it.
pub fn fingerprint_for_line(line: &str) -> Option<String> {
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() < 2 {
        return None;
    }
    let blob = decode_base64_strict(parts[1])?;
    let digest = Sha256::digest(&blob);
    let encoded = STANDARD.encode(digest);
    Some(format!("SHA256:{}", encoded.trim_end_matches('=')))
}

/// The fingerprint of a public key file, or None if it cannot be read.
pub fn fingerprint_for_file(path: &Path) -> Option<String> {
    let text = std::fs::read_to_string(path).ok()?;
    fingerprint_for_line(&text)
}

/// Strict base64: the alphabet only, and a length that is a multiple of four,
/// the way `base64.b64decode(text, validate=True)` takes it.
fn decode_base64_strict(text: &str) -> Option<Vec<u8>> {
    if !text.len().is_multiple_of(4) {
        return None;
    }
    STANDARD.decode(text).ok()
}

// --------------------------------------------------------------------------
// The local record
// --------------------------------------------------------------------------

/// Where the local key record lives. Reading it must not create anything.
fn record_path() -> PathBuf {
    config_dir().join("keys.json")
}

/// The record: `{"version": 1, "environments": {<env>: {fingerprint, path}}}`.
/// No key material in it, ever.
pub fn load_record() -> Value {
    let text = std::fs::read_to_string(record_path()).unwrap_or_default();
    match serde_json::from_str::<Value>(&text) {
        Ok(v) if v.is_object() => v,
        _ => Value::Object(Map::new()),
    }
}

/// Write the record atomically at mode 0600, in a 0700 directory.
pub fn save_record(data: &Value) -> Result<()> {
    ensure_config_dir();
    let path = record_path();
    let mut tmp_name = path
        .file_name()
        .map(|n| n.to_os_string())
        .unwrap_or_else(|| std::ffi::OsString::from("keys.json"));
    tmp_name.push(format!(".{}.tmp", std::process::id()));
    let temporary = path.with_file_name(tmp_name);

    let mut text = serde_json::to_string_pretty(data)
        .map_err(|e| freepod(format!("cannot serialize the key record: {e}")))?;
    text.push('\n');

    std::fs::write(&temporary, text.as_bytes())
        .map_err(|e| freepod(format!("cannot write {}: {e}", temporary.display())))?;
    set_mode(&temporary, 0o600);
    std::fs::rename(&temporary, &path)
        .map_err(|e| freepod(format!("cannot write {}: {e}", path.display())))?;
    set_mode(&path, 0o600);
    Ok(())
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) {
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(mode));
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) {}

/// This machine's recorded key for one environment: fingerprint and path.
///
/// Keyed by environment because an account on dev is not the account on prod;
/// a key registered against one must never be offered as this machine's key
/// for the other.
pub fn local_key(env: &str) -> Option<(String, String)> {
    let record = load_record();
    let entry = record.get("environments")?.get(env)?;
    let fingerprint = entry.get("fingerprint")?.as_str()?.to_string();
    let path = entry.get("path")?.as_str()?.to_string();
    Some((fingerprint, path))
}

pub fn remember(env: &str, fingerprint: &str, path: &Path) -> Result<()> {
    let mut data = load_record();
    let environments = data
        .as_object_mut()
        .ok_or_else(|| freepod("the key record is malformed"))?
        .entry("environments")
        .or_insert_with(|| Value::Object(Map::new()));
    if !environments.is_object() {
        *environments = Value::Object(Map::new());
    }
    environments.as_object_mut().unwrap().insert(
        env.to_string(),
        json!({ "fingerprint": fingerprint, "path": path.to_string_lossy() }),
    );
    data["version"] = json!(RECORD_VERSION);
    save_record(&data)
}

/// Drop the record for one environment; a no-op when there is none.
pub fn forget(env: &str) -> Result<()> {
    let mut data = load_record();
    let Some(environments) = data.get_mut("environments").and_then(|v| v.as_object_mut()) else {
        return Ok(());
    };
    if environments.remove(env).is_none() {
        return Ok(());
    }
    save_record(&data)
}

// --------------------------------------------------------------------------
// Generation and reading
// --------------------------------------------------------------------------

pub fn generated_key_path() -> PathBuf {
    config_dir().join(GENERATED_KEY_NAME)
}

/// Write an Ed25519 keypair at `path`, 0600, and return its public line.
///
/// Generated by `ssh-keygen` rather than by a crypto library: it is already
/// present wherever these keys will be used, it writes exactly the on-disk
/// format OpenSSH expects, and it keeps the client's dependencies to the
/// three it ships with.
///
/// No passphrase: a prompt on every command that opens a connection is
/// hostile to a tool meant to be scriptable. The mitigation is that the key
/// is per machine and independently revocable — a user wanting a passphrase
/// or a hardware token registers their own key instead.
pub fn generate_keypair(path: &Path) -> Result<String> {
    ensure_config_dir();
    let comment = format!("freepod@{}", hostname());
    let output = std::process::Command::new("ssh-keygen")
        .arg("-t")
        .arg("ed25519")
        .arg("-N")
        .arg("")
        .arg("-C")
        .arg(&comment)
        .arg("-f")
        .arg(path)
        .output()
        .map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                freepod(
                    "ssh-keygen was not found, so no key could be generated. Install \
                     OpenSSH, or register a key you already have with `freepod key add \
                     <path to .pub>`.",
                )
            } else {
                freepod(format!("cannot run ssh-keygen: {e}"))
            }
        })?;
    if !output.status.success() {
        let detail = if output.stderr.is_empty() {
            String::from_utf8_lossy(&output.stdout)
        } else {
            String::from_utf8_lossy(&output.stderr)
        };
        return Err(freepod(format!(
            "ssh-keygen failed: {}",
            detail.trim().chars().take(300).collect::<String>()
        )));
    }

    set_mode(path, 0o600);
    let mut public = path.as_os_str().to_os_string();
    public.push(".pub");
    let public = PathBuf::from(public);
    let text = std::fs::read_to_string(&public)
        .map_err(|e| freepod(format!("cannot read {}: {e}", public.display())))?;
    Ok(text.trim().to_string())
}

/// The public key line at `path`, refusing a private key file.
pub fn read_public_key(path: &Path) -> Result<String> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| usage(format!("cannot read {}: {e}", path.display())))?;

    if text.contains("PRIVATE KEY") {
        return Err(usage(format!(
            "{} is a private key. Register the public half instead: {}.pub — and \
             never share the private one.",
            path.display(),
            path.display()
        )));
    }
    if fingerprint_for_line(&text).is_none() {
        return Err(usage(format!(
            "{} is not an OpenSSH public key file",
            path.display()
        )));
    }
    Ok(text.trim().to_string())
}

// --------------------------------------------------------------------------
// Recovery
// --------------------------------------------------------------------------

/// Where a user's own keys live. Read for recovery; never written to.
///
/// Resolved per call, like `config_dir()`: binding it at startup would freeze
/// whatever `HOME` happened to be then.
pub fn ssh_dir() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/"))
        .join(".ssh")
}

/// Public key files this machine offers, client-owned ones first.
///
/// Public files, never private ones: a key held in an agent or on a hardware
/// token has no private file at all, and `ssh -i <public key>` with
/// `IdentitiesOnly=yes` is the documented way to select such an identity.
pub fn candidate_public_keys() -> Vec<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    let mut generated = generated_key_path().into_os_string();
    generated.push(".pub");
    let generated = PathBuf::from(generated);
    if generated.is_file() {
        candidates.push(generated);
    }
    let user_keys = ssh_dir();
    if user_keys.is_dir() {
        let mut paths: Vec<PathBuf> = std::fs::read_dir(&user_keys)
            .into_iter()
            .flatten()
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|ext| ext == "pub") && p.is_file())
            .collect();
        paths.sort();
        candidates.extend(paths);
    }
    candidates
}

/// Local public key files whose fingerprint the account has registered.
pub fn recover(registered: &[Value]) -> Vec<PathBuf> {
    let known: HashSet<String> = registered
        .iter()
        .filter_map(|k| {
            k.get("fingerprint")
                .and_then(|v| v.as_str())
                .map(String::from)
        })
        .collect();
    candidate_public_keys()
        .into_iter()
        .filter(|p| {
            fingerprint_for_file(p)
                .as_deref()
                .is_some_and(|f| known.contains(f))
        })
        .collect()
}

/// The key this machine should offer, adopting one by fingerprint if needed.
///
/// Never adopts on a near match: exactly one candidate, or the caller is asked.
pub fn resolve_local_key(env: &str, registered: &[Value]) -> Result<PathBuf> {
    if let Some((fingerprint, path)) = local_key(env) {
        let path = PathBuf::from(&path);
        if fingerprint_for_file(&path).as_deref() == Some(fingerprint.as_str())
            && registered.iter().any(|k| {
                k.get("fingerprint").and_then(|v| v.as_str()) == Some(fingerprint.as_str())
            })
        {
            return Ok(path);
        }
    }

    let matches = recover(registered);
    if matches.len() == 1 {
        let path = matches.into_iter().next().unwrap();
        let fingerprint = fingerprint_for_file(&path)
            .ok_or_else(|| freepod("the matching key can no longer be read"))?;
        remember(env, &fingerprint, &path)?;
        return Ok(path);
    }
    if matches.is_empty() {
        return Err(freepod(
            "no registered SSH key is available on this machine. Register one with \
             `freepod key add`.",
        ));
    }
    let listed = matches
        .iter()
        .map(|p| p.display().to_string())
        .collect::<Vec<_>>()
        .join("\n  ");
    Err(freepod(format!(
        "several local keys are registered on this account; name the one to use \
         with `freepod key add <path>`:\n  {listed}"
    )))
}

// --------------------------------------------------------------------------
// The platform collection
// --------------------------------------------------------------------------

fn base(user_id: u64) -> String {
    format!("/api/users/{user_id}/ssh-keys")
}

pub async fn list_keys(api: &mut ApiClient, user_id: u64) -> Result<Vec<Value>> {
    let body = api.get_json(&base(user_id), None).await?;
    let arr = body
        .as_array()
        .ok_or_else(|| freepod(format!("unexpected ssh-keys response: {body}")))?;
    Ok(arr.clone())
}

/// Register a public key; the stored key object, which carries the
/// fingerprint and the label the platform settled on.
pub async fn add_key(
    api: &mut ApiClient,
    user_id: u64,
    public_key: &str,
    label: Option<&str>,
) -> Result<Value> {
    let mut payload = json!({ "public_key": public_key });
    if let Some(label) = label {
        payload["label"] = json!(label);
    }
    let response = api.post_json(&base(user_id), Some(&payload)).await?;
    if !response.is_success() {
        return Err(refusal(&response));
    }
    response.decode()
}

pub async fn remove_key(api: &mut ApiClient, user_id: u64, fingerprint: &str) -> Result<()> {
    let response = api
        .delete(&format!(
            "{}/{}",
            base(user_id),
            encode_segment(fingerprint)
        ))
        .await?;
    if !response.is_success() {
        return Err(refusal(&response));
    }
    Ok(())
}

/// The platform's own words, which already name the failing check.
fn refusal(response: &ApiResponse) -> Error {
    let text = response.text();
    let detail = match serde_json::from_str::<Value>(&text) {
        Ok(Value::Object(obj)) => obj
            .get("detail")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        Ok(_) => String::new(),
        Err(_) => text.trim().chars().take(300).collect(),
    };
    if detail.is_empty() {
        freepod(format!(
            "the platform refused the request: HTTP {}",
            response.status
        ))
    } else {
        freepod(detail)
    }
}

// --------------------------------------------------------------------------
// Output
// --------------------------------------------------------------------------

/// One row per registered key; the local key is marked with `*`.
pub fn render_table(keys: &[Value], local_fingerprint: Option<&str>) -> String {
    if keys.is_empty() {
        return String::new();
    }
    let mut table: Vec<Vec<String>> = vec![COLUMNS.iter().map(|s| s.to_string()).collect()];
    for key in keys {
        let fingerprint = key
            .get("fingerprint")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let here = if local_fingerprint.is_some_and(|l| l == fingerprint) {
            "*".to_string()
        } else {
            BLANK.to_string()
        };
        table.push(vec![
            here,
            if fingerprint.is_empty() {
                BLANK.to_string()
            } else {
                fingerprint.to_string()
            },
            key.get("label")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .map(String::from)
                .unwrap_or_else(|| BLANK.to_string()),
            key.get("key_type")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .map(String::from)
                .unwrap_or_else(|| BLANK.to_string()),
            format_time(key.get("created_at").unwrap_or(&Value::Null)),
        ]);
    }
    render(&table)
}

/// The machine's own name for the generated key's comment, or `freepod`.
fn hostname() -> String {
    #[cfg(unix)]
    {
        let mut uts: libc::utsname = unsafe { std::mem::zeroed() };
        if unsafe { libc::uname(&mut uts) } == 0 {
            let name = uts
                .nodename
                .iter()
                .take_while(|&&c| c != 0)
                .map(|&c| c as u8)
                .collect::<Vec<u8>>();
            if !name.is_empty() {
                return String::from_utf8_lossy(&name).to_string();
            }
        }
    }
    "freepod".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    use crate::testutil::ENV_LOCK;

    struct IsolatedHome {
        home: PathBuf,
        config: PathBuf,
        _guard: std::sync::MutexGuard<'static, ()>,
    }

    impl IsolatedHome {
        fn new(tag: &str) -> Self {
            let guard = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
            let pid = std::process::id();
            let home = std::env::temp_dir().join(format!("freepod-keys-home-{tag}-{pid}"));
            let config = std::env::temp_dir().join(format!("freepod-keys-xdg-{tag}-{pid}"));
            let _ = std::fs::remove_dir_all(&home);
            let _ = std::fs::remove_dir_all(&config);
            std::fs::create_dir_all(&home).unwrap();
            std::fs::create_dir_all(&config).unwrap();
            std::env::set_var("HOME", &home);
            std::env::set_var("XDG_CONFIG_HOME", &config);
            Self {
                home,
                config,
                _guard: guard,
            }
        }

        fn cleanup(&self) {
            std::env::remove_var("HOME");
            std::env::remove_var("XDG_CONFIG_HOME");
            let _ = std::fs::remove_dir_all(&self.home);
            let _ = std::fs::remove_dir_all(&self.config);
        }
    }

    /// A real keypair on disk; returns the public key path. Skips the test
    /// when `ssh-keygen` is absent.
    fn generate(directory: &Path, name: &str, comment: &str) -> Option<PathBuf> {
        std::fs::create_dir_all(directory).ok()?;
        let path = directory.join(name);
        let output = std::process::Command::new("ssh-keygen")
            .arg("-t")
            .arg("ed25519")
            .arg("-N")
            .arg("")
            .arg("-C")
            .arg(comment)
            .arg("-f")
            .arg(&path)
            .output()
            .ok()?;
        if !output.status.success() {
            return None;
        }
        let mut pub_path = path.as_os_str().to_os_string();
        pub_path.push(".pub");
        Some(PathBuf::from(pub_path))
    }

    fn registered(public_path: &Path, label: &str) -> Value {
        let line = std::fs::read_to_string(public_path)
            .unwrap()
            .trim()
            .to_string();
        let mut parts = line.split_whitespace();
        let key_type = parts.next().unwrap_or("ssh-ed25519").to_string();
        json!({
            "fingerprint": fingerprint_for_line(&line),
            "key_type": key_type,
            "bits": 256,
            "label": label,
            "public_key": line,
            "created_at": "2026-08-27T10:00:00"
        })
    }

    // --- Fingerprints ------------------------------------------------------

    #[test]
    fn fingerprint_matches_ssh_keygen() {
        let dir = std::env::temp_dir().join(format!("freepod-keys-fp-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let pub_path = match generate(&dir, "id_ed25519", "me@here") {
            Some(p) => p,
            None => return, // no ssh-keygen on this machine
        };
        let reported = std::process::Command::new("ssh-keygen")
            .arg("-lf")
            .arg(&pub_path)
            .output()
            .ok()
            .and_then(|o| String::from_utf8(o.stdout).ok())
            .and_then(|out| out.split_whitespace().nth(1).map(String::from));
        assert_eq!(fingerprint_for_file(&pub_path), reported);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn fingerprint_of_nonsense_is_none() {
        assert_eq!(fingerprint_for_line("not a key"), None);
        assert_eq!(fingerprint_for_line(""), None);
        assert_eq!(fingerprint_for_line("onepart"), None);
    }

    #[test]
    fn fingerprint_rejects_invalid_base64() {
        // A second field that is not base64 at all.
        assert_eq!(
            fingerprint_for_line("ssh-ed25519 !!!not-base64!!! x@y"),
            None
        );
        // Valid base64 but a length that cannot carry a blob.
        assert_eq!(fingerprint_for_line("ssh-ed25519 AAA x@y"), None);
    }

    // --- The local record --------------------------------------------------

    #[test]
    fn record_loads_empty_when_missing_and_creates_nothing() {
        let home = IsolatedHome::new("missing");
        assert!(load_record().is_object());
        assert!(!record_path().exists());
        home.cleanup();
    }

    #[test]
    fn record_loads_empty_when_corrupt() {
        let home = IsolatedHome::new("corrupt");
        ensure_config_dir();
        std::fs::write(record_path(), "this is not json").unwrap();
        assert!(load_record().is_object());
        assert!(load_record().get("environments").is_none());
        home.cleanup();
    }

    #[test]
    fn record_holds_no_key_material() {
        let home = IsolatedHome::new("material");
        remember("prod", "SHA256:abc123", Path::new("/tmp/id_ed25519.pub")).unwrap();
        let text = std::fs::read_to_string(record_path()).unwrap();
        assert!(!text.contains("PRIVATE KEY"));
        assert!(!text.contains("ssh-ed25519"));
        assert!(text.contains("SHA256:abc123"));
        home.cleanup();
    }

    #[test]
    fn record_is_written_owner_only() {
        let home = IsolatedHome::new("mode");
        remember("prod", "SHA256:abc123", Path::new("/tmp/id_ed25519.pub")).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(record_path())
                .unwrap()
                .permissions()
                .mode();
            assert_eq!(mode & 0o777, 0o600);
        }
        home.cleanup();
    }

    #[test]
    fn environments_do_not_share_a_record() {
        let home = IsolatedHome::new("envs");
        remember("dev", "SHA256:abc123", Path::new("/tmp/id_ed25519.pub")).unwrap();
        assert!(local_key("dev").is_some());
        assert!(local_key("prod").is_none());
        home.cleanup();
    }

    #[test]
    fn record_survives_across_invocations() {
        let home = IsolatedHome::new("survive");
        remember("prod", "SHA256:abc123", Path::new("/tmp/id_ed25519.pub")).unwrap();
        let (fingerprint, path) = local_key("prod").unwrap();
        assert_eq!(fingerprint, "SHA256:abc123");
        assert_eq!(path, "/tmp/id_ed25519.pub");
        // A second save over the first keeps the record intact.
        remember("prod", "SHA256:def456", Path::new("/tmp/other.pub")).unwrap();
        assert_eq!(local_key("prod").unwrap().0, "SHA256:def456");
        home.cleanup();
    }

    #[test]
    fn forget_is_a_noop_when_absent() {
        let home = IsolatedHome::new("forget");
        assert!(forget("prod").is_ok());
        assert!(local_key("prod").is_none());
        home.cleanup();
    }

    // --- Reading ------------------------------------------------------------

    #[test]
    fn read_public_key_returns_the_trimmed_line() {
        let dir = std::env::temp_dir().join(format!("freepod-keys-read-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let pub_path = dir.join("id_ed25519.pub");
        // A valid base64 blob: the fingerprint, not the key, is under test.
        let line = "ssh-ed25519 aGVsbG8gd29ybGQ= x@y";
        std::fs::write(&pub_path, format!("  {line}\n\n")).unwrap();
        assert_eq!(read_public_key(&pub_path).unwrap(), line);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn read_public_key_refuses_a_private_key_file() {
        let dir = std::env::temp_dir().join(format!("freepod-keys-priv-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let private = dir.join("id_ed25519");
        std::fs::write(
            &private,
            "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n",
        )
        .unwrap();
        let err = read_public_key(&private).unwrap_err();
        assert!(matches!(err, Error::Usage(_)));
        let message = err.message().to_string();
        assert!(message.contains("private key"));
        assert!(message.ends_with(".pub") || message.contains("id_ed25519.pub"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn read_public_key_refuses_non_key_text() {
        let dir = std::env::temp_dir().join(format!("freepod-keys-notkey-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("notes.txt");
        std::fs::write(&path, "hello world\n").unwrap();
        let err = read_public_key(&path).unwrap_err();
        assert!(matches!(err, Error::Usage(_)));
        assert!(err.message().contains("not an OpenSSH public key file"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn read_public_key_missing_file_is_a_usage_error() {
        let err = read_public_key(Path::new("/nonexistent/id_ed25519.pub")).unwrap_err();
        assert!(matches!(err, Error::Usage(_)));
        assert!(err.message().starts_with("cannot read"));
    }

    // --- Recovery ------------------------------------------------------------

    #[test]
    fn recovery_adopts_a_single_matching_key() {
        let home = IsolatedHome::new("adopt");
        let pub_path = generate(&home.home.join(".ssh"), "id_ed25519", "me@here").unwrap();
        let entry = registered(&pub_path, "me@here");
        let fingerprint = entry["fingerprint"].as_str().unwrap().to_string();
        assert_eq!(resolve_local_key("prod", &[entry]).unwrap(), pub_path);
        assert_eq!(local_key("prod").unwrap().0, fingerprint);
        home.cleanup();
    }

    #[test]
    fn recovery_works_without_the_private_half() {
        let home = IsolatedHome::new("pubonly");
        let pub_path = generate(&home.home.join(".ssh"), "id_ed25519", "me@here").unwrap();
        let private = pub_path.with_file_name(
            pub_path
                .file_name()
                .unwrap()
                .to_str()
                .unwrap()
                .trim_end_matches(".pub"),
        );
        let _ = std::fs::remove_file(&private);
        let entry = registered(&pub_path, "me@here");
        assert_eq!(resolve_local_key("prod", &[entry]).unwrap(), pub_path);
        home.cleanup();
    }

    #[test]
    fn recovery_reports_when_nothing_matches() {
        let home = IsolatedHome::new("nomatch");
        generate(&home.home.join(".ssh"), "id_ed25519", "me@here").unwrap();
        let other_dir =
            std::env::temp_dir().join(format!("freepod-keys-else-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&other_dir);
        let other = generate(&other_dir, "other", "else@where").unwrap();
        let err = resolve_local_key("prod", &[registered(&other, "else@where")]).unwrap_err();
        assert!(matches!(err, Error::Freepod(_)));
        assert!(err.message().contains("freepod key add"));
        let _ = std::fs::remove_dir_all(&other_dir);
        home.cleanup();
    }

    #[test]
    fn recovery_asks_when_several_match() {
        let home = IsolatedHome::new("several");
        let first = generate(&home.home.join(".ssh"), "id_ed25519", "one@here").unwrap();
        let second = generate(&home.home.join(".ssh"), "id_other", "two@here").unwrap();
        let err = resolve_local_key(
            "prod",
            &[registered(&first, "one"), registered(&second, "two")],
        )
        .unwrap_err();
        assert!(matches!(err, Error::Freepod(_)));
        let message = err.message().to_string();
        assert!(message.contains("several"));
        assert!(message.contains(first.display().to_string().as_str()));
        assert!(message.contains(second.display().to_string().as_str()));
        home.cleanup();
    }

    #[test]
    fn recovery_ignores_a_stale_record() {
        let home = IsolatedHome::new("stale");
        let stale_dir =
            std::env::temp_dir().join(format!("freepod-keys-gone-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&stale_dir);
        let stale = generate(&stale_dir, "stale", "old@here").unwrap();
        let live = generate(&home.home.join(".ssh"), "id_ed25519", "me@here").unwrap();
        remember(
            "prod",
            fingerprint_for_file(&stale).as_deref().unwrap(),
            &stale,
        )
        .unwrap();

        assert_eq!(
            resolve_local_key("prod", &[registered(&live, "me@here")]).unwrap(),
            live
        );
        assert_eq!(local_key("prod").unwrap().1, live.to_string_lossy());
        let _ = std::fs::remove_dir_all(&stale_dir);
        home.cleanup();
    }

    #[test]
    fn candidates_are_public_files_only() {
        let home = IsolatedHome::new("cands");
        generate(&home.home.join(".ssh"), "id_ed25519", "me@here").unwrap();
        let candidates = candidate_public_keys();
        assert!(!candidates.is_empty());
        assert!(candidates
            .iter()
            .all(|p| p.extension().is_some_and(|e| e == "pub")));
        home.cleanup();
    }

    // --- Generation ----------------------------------------------------------

    #[test]
    fn generate_keypair_writes_owner_only_and_never_to_dot_ssh() {
        let home = IsolatedHome::new("gen");
        let target = home.config.join("id_ed25519");
        let public_line = match generate_keypair(&target) {
            Ok(line) => line,
            Err(Error::Freepod(m)) if m.contains("ssh-keygen was not found") => return,
            Err(e) => panic!("unexpected error: {e:?}"),
        };
        assert!(target.is_file());
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(&target).unwrap().permissions().mode();
            assert_eq!(mode & 0o777, 0o600);
        }
        assert!(public_line.starts_with("ssh-ed25519 "));
        assert!(fingerprint_for_line(&public_line).is_some());
        assert!(!home.home.join(".ssh").exists());
        home.cleanup();
    }

    // --- Output ---------------------------------------------------------------

    #[test]
    fn render_table_marks_the_local_key() {
        let keys = vec![
            json!({ "fingerprint": "SHA256:aaa", "label": "one", "key_type": "ssh-ed25519",
                    "created_at": "2026-08-27T10:00:00" }),
            json!({ "fingerprint": "SHA256:bbb", "label": "two", "key_type": "ssh-ed25519",
                    "created_at": "2026-08-27T11:00:00" }),
        ];
        let table = render_table(&keys, Some("SHA256:bbb"));
        let lines: Vec<&str> = table.lines().collect();
        assert!(lines[0].contains("FINGERPRINT"));
        assert!(!lines[1].starts_with('*'));
        assert!(lines[2].starts_with('*'));
        assert!(table.contains("SHA256:aaa"));
        assert!(table.contains("one"));
    }

    #[test]
    fn render_table_blanks_missing_fields() {
        let keys = vec![json!({ "fingerprint": "SHA256:aaa" })];
        let table = render_table(&keys, None);
        let line = table.lines().nth(1).unwrap();
        assert!(line.contains(BLANK));
    }

    #[test]
    fn render_table_empty_input_is_empty() {
        assert_eq!(render_table(&[], None), "");
    }
}
