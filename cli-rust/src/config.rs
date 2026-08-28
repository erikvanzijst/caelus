//! Environments and on-disk locations.
//!
//! The client targets one of exactly two named environments. There is no
//! caller-supplied base URL: an access token is bound by its audience to one
//! environment. Mirrors `config.py`.

use std::collections::HashMap;
use std::path::PathBuf;

use crate::errors::{usage, Result};

pub const ISSUER: &str = "https://keycloak.freepod.eu/realms/freepod";

pub const DEFAULT_ENV: &str = "prod";

/// Selects the environment when no explicit choice is made.
pub const ENV_VAR: &str = "FREEPOD_ENV";

/// The stable slug of the product that runs tenant-supplied images.
pub const CUSTOM_PRODUCT_SLUG: &str = "custom";

pub const SCOPES: &str = "openid email profile offline_access";
pub const DEVICE_GRANT: &str = "urn:ietf:params:oauth:grant-type:device_code";

pub const USER_AGENT: &str = concat!("freepod/", env!("CARGO_PKG_VERSION"), " (+https://freepod.eu)");

/// How long a single HTTP request may take.
pub const DEFAULT_HTTP_TIMEOUT: u64 = 30;

/// Read timeout for a followed log stream.
pub const LOG_STREAM_READ_TIMEOUT: u64 = 120;

/// Reconnection attempts for an interrupted followed stream, and the first
/// backoff interval, which doubles.
pub const LOG_RECONNECT_ATTEMPTS: u32 = 5;
pub const LOG_RECONNECT_BACKOFF_SECONDS: f64 = 1.0;

/// Per-operation wait defaults.
pub const LOGIN_WAIT_SECONDS: u64 = 300;
pub const BUILD_WAIT_SECONDS: u64 = 1800;
pub const ROLLOUT_WAIT_SECONDS: u64 = 600;

/// Resolve a bounded wait: the global `--timeout` if given, else the
/// operation's own default.
pub fn wait_seconds(override_secs: Option<u64>, default: u64) -> Result<u64> {
    match override_secs {
        None => Ok(default),
        Some(0) => Err(usage("--timeout must be a positive number of seconds")),
        Some(v) => Ok(v),
    }
}

/// One named Freepod instance and the OAuth2 client that reaches it.
#[derive(Debug, Clone)]
pub struct Environment {
    pub name: &'static str,
    pub client_id: &'static str,
    pub api_base: String,
    pub issuer: String,
}

impl Environment {
    pub fn authorization_endpoint(&self) -> String {
        format!("{}/protocol/openid-connect/auth", self.issuer)
    }
    pub fn device_endpoint(&self) -> String {
        format!("{}/protocol/openid-connect/auth/device", self.issuer)
    }
    pub fn token_endpoint(&self) -> String {
        format!("{}/protocol/openid-connect/token", self.issuer)
    }
    /// The Keycloak group this environment gates access on, if any.
    pub fn requires_group(&self) -> Option<&str> {
        if self.name == "dev" {
            Some("freepod-dev")
        } else {
            None
        }
    }
    pub fn url(&self, path: &str) -> String {
        format!("{}{}", self.api_base, path)
    }
}

fn env_map() -> HashMap<&'static str, Environment> {
    let mut m = HashMap::new();
    m.insert(
        "prod",
        Environment {
            name: "prod",
            client_id: "freepod-cli-prod",
            api_base: "https://freepod.eu".to_string(),
            issuer: ISSUER.to_string(),
        },
    );
    m.insert(
        "dev",
        Environment {
            name: "dev",
            client_id: "freepod-cli-dev",
            api_base: "https://dev.freepod.eu".to_string(),
            issuer: ISSUER.to_string(),
        },
    );
    m
}

pub fn environments() -> HashMap<&'static str, Environment> {
    env_map()
}

/// The accepted values, for use in a usage error.
pub fn environment_names() -> String {
    let mut names: Vec<&str> = environments().keys().copied().collect();
    names.sort();
    names.join(", ")
}

/// Pick the environment: explicit selection, then the project file, then
/// `FREEPOD_ENV`, then prod.
pub fn resolve_environment(
    selected: Option<&str>,
    project_env: Option<&str>,
) -> Result<Environment> {
    let name = match (selected, project_env) {
        (Some(s), _) if !s.is_empty() => s.to_string(),
        (Some(_), _) => {
            // An empty explicit value is handled by the caller; treat as unset.
            project_env
                .map(|p| p.to_string())
                .or_else(|| std::env::var(ENV_VAR).ok())
                .unwrap_or_else(|| DEFAULT_ENV.to_string())
        }
        (None, Some(p)) => p.to_string(),
        (None, None) => std::env::var(ENV_VAR).unwrap_or_else(|_| DEFAULT_ENV.to_string()),
    };
    let name = name.trim().to_string();
    let envs = environments();
    match envs.get(name.as_str()) {
        Some(e) => Ok(e.clone()),
        None => {
            let source = if selected.is_some() {
                "--env"
            } else if project_env.is_some() {
                crate::project::PROJECT_FILE
            } else {
                ENV_VAR
            };
            Err(usage(format!(
                "unknown environment '{}' for {} — accepted values are {}",
                name,
                source,
                environment_names()
            )))
        }
    }
}

fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/"))
}

/// Resolve `${XDG_CONFIG_HOME:-~/.config}/freepod` without touching disk.
pub fn config_dir() -> PathBuf {
    let base = std::env::var("XDG_CONFIG_HOME")
        .ok()
        .map(PathBuf::from)
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| home_dir().join(".config"));
    base.join("freepod")
}

/// The config directory, created owner-only.
pub fn ensure_config_dir() -> PathBuf {
    let directory = config_dir();
    if let Err(e) = std::fs::create_dir_all(&directory) {
        eprintln!("warning: could not create config dir {}: {}", directory.display(), e);
    }
    // Assert the mode on a directory that already existed too.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&directory, std::fs::Permissions::from_mode(0o700));
    }
    directory
}

/// Where the credential cache lives. Reading it must not create anything.
pub fn token_cache_path() -> PathBuf {
    config_dir().join("tokens.json")
}

/// The cache path as a string, for messages. Creates nothing.
pub fn cache_path_hint() -> String {
    token_cache_path().to_string_lossy().to_string()
}
