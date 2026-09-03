//! OAuth2 flows, the token cache, and the session that renews a credential.
//!
//! Two flows:
//!
//! * **loopback** — authorization code + PKCE, with the code arriving on a
//!   listener bound to an ephemeral port on `127.0.0.1`. Needs a browser on
//!   this machine that can reach that interface.
//! * **device** — the device authorization grant, approved on any other device.
//!
//! The flow is auto-detected and overridable. Mirrors `auth.py`.

use std::collections::HashMap;
use std::io::Read;
use std::net::TcpListener;
use std::time::{Duration, Instant};

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use rand::RngCore;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::config::{
    ensure_config_dir, token_cache_path, Environment, SCOPES, USER_AGENT,
};
use crate::errors::{authentication, freepod, Result};

/// The registered redirect URIs are the port-less forms. Keycloak relaxes
/// *port* matching for loopback hosts (RFC 8252 section 7.3), so any ephemeral
/// port matches — but the path is matched exactly. Do not change this.
const CALLBACK_PATH: &str = "/callback";
const CALLBACK_HOST: &str = "127.0.0.1";

const CACHE_VERSION: u64 = 1;

/// Diagnostics go to stderr so stdout carries only results.
pub fn log(message: &str) {
    eprintln!("{message}");
}

/// An OAuth2 error response, carrying the machine-readable `error` code.
#[derive(Debug)]
pub struct OAuthError {
    pub message: String,
    pub code: Option<String>,
}

impl std::fmt::Display for OAuthError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

// --------------------------------------------------------------------------
// PKCE and token inspection
// --------------------------------------------------------------------------

pub fn b64url(raw: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(raw)
}

/// Return (code_verifier, code_challenge) for the S256 method.
pub fn pkce_pair() -> (String, String) {
    let mut bytes = [0u8; 64];
    rand::thread_rng().fill_bytes(&mut bytes);
    let verifier = b64url(&bytes);
    let mut hasher = Sha256::new();
    hasher.update(verifier.as_bytes());
    let challenge = b64url(hasher.finalize().as_slice());
    (verifier, challenge)
}

/// Build a `key=value&key=value` query string, percent-encoding each part.
fn query_pairs(pairs: &[(&str, &str)]) -> String {
    use url::form_urlencoded::byte_serialize;
    let mut out = String::new();
    for (i, (k, v)) in pairs.iter().enumerate() {
        if i > 0 {
            out.push('&');
        }
        out.extend(byte_serialize(k.as_bytes()));
        out.push('=');
        out.extend(byte_serialize(v.as_bytes()));
    }
    out
}

/// Decode a JWT payload *without verifying it* — for display only.
pub fn decode_claims(jwt: &str) -> Value {
    let parts: Vec<&str> = jwt.split('.').collect();
    if parts.len() < 2 {
        return json!({});
    }
    match URL_SAFE_NO_PAD.decode(parts[1].as_bytes()) {
        Ok(decoded) => serde_json::from_slice(&decoded).unwrap_or(json!({})),
        Err(_) => json!({}),
    }
}

/// A claim value the way Python's `str()` renders it: a bare string unquoted,
/// a list as `['a', 'b']`, a bool as `True`/`False`.
fn py_repr(v: &Value) -> String {
    match v {
        Value::String(s) => format!("'{s}'"),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => if *b { "True".into() } else { "False".into() },
        Value::Null => "None".into(),
        Value::Array(arr) => {
            let items: Vec<String> = arr.iter().map(py_repr).collect();
            format!("[{}]", items.join(", "))
        }
        Value::Object(obj) => {
            let items: Vec<String> = obj
                .iter()
                .map(|(k, val)| format!("'{k}': {}", py_repr(val)))
                .collect();
            format!("{{{}}}", items.join(", "))
        }
    }
}

/// Top-level: a string is printed bare; anything else as `py_repr`.
fn py_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        other => py_repr(other),
    }
}

/// Format an epoch second the way Python's
/// `time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(secs))` does: the
/// local wall-clock time with the operating system's zone abbreviation
/// (`UTC`, `EDT`, …). chrono would render a numeric offset (`-04:00`) instead,
/// so we call the same libc functions Python does to stay byte-identical.
fn local_timestamp(secs: i64) -> String {
    use std::ffi::CString;
    use std::mem::zeroed;

    let fmt = CString::new("%Y-%m-%d %H:%M:%S %Z").unwrap();
    let mut tm: libc::tm = unsafe { zeroed() };
    unsafe {
        if libc::localtime_r(&secs, &mut tm).is_null() {
            return String::new();
        }
        let mut buf = [0u8; 64];
        let n = libc::strftime(
            buf.as_mut_ptr().cast::<libc::c_char>(),
            buf.len(),
            fmt.as_ptr(),
            &tm,
        );
        String::from_utf8_lossy(&buf[..n as usize]).into_owned()
    }
}

/// Render the interesting claims for `--verbose`.
pub fn format_claims(access_token: &str) -> String {
    let claims = decode_claims(access_token);
    let obj = match claims.as_object() {
        Some(o) if !o.is_empty() => o,
        _ => return "  (could not decode the access token payload)".to_string(),
    };

    let mut lines = vec!["  Access token claims (unverified, for display only):".to_string()];
    for name in [
        "iss", "azp", "aud", "sub", "email", "preferred_username", "groups", "scope",
    ] {
        if let Some(v) = obj.get(name) {
            lines.push(format!("    {:<20} {}", name, py_str(v)));
        }
    }
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    for name in ["iat", "exp"] {
        if let Some(v) = obj.get(name).and_then(|v| v.as_u64()) {
            lines.push(format!("    {:<20} {} ({})", name, v, local_timestamp(v as i64)));
        }
    }
    if let Some(exp) = obj.get("exp").and_then(|v| v.as_u64()) {
        lines.push(format!(
            "    {:<20} {}s",
            "expires in",
            exp as i64 - now as i64
        ));
    }
    lines.join("\n")
}

// --------------------------------------------------------------------------
// Keycloak calls
// --------------------------------------------------------------------------

/// POST an `application/x-www-form-urlencoded` body and parse the reply.
pub async fn post_form(
    client: &reqwest::Client,
    url: &str,
    fields: &HashMap<String, String>,
) -> std::result::Result<Value, OAuthError> {
    let mut form = Vec::new();
    for (k, v) in fields {
        form.push((k.clone(), v.clone()));
    }
    let response = client
        .post(url)
        .form(&form)
        .header("Accept", "application/json")
        .header("User-Agent", USER_AGENT)
        .send()
        .await
        .map_err(|e| OAuthError {
            message: format!("cannot reach {url}: {e}"),
            code: None,
        })?;

    let status = response.status().as_u16();
    let raw = response
        .text()
        .await
        .map_err(|e| OAuthError {
            message: format!("cannot read response: {e}"),
            code: None,
        })?;

    if status < 400 {
        return serde_json::from_str(&raw)
            .map_err(|_| OAuthError {
                message: format!("unparseable response from {url}"),
                code: None,
            });
    }

    match serde_json::from_str::<Value>(&raw) {
        Ok(payload) => {
            let code = payload.get("error").and_then(|v| v.as_str()).map(|s| s.to_string());
            let description = payload
                .get("error_description")
                .and_then(|v| v.as_str())
                .or(code.as_deref())
                .map(|s| s.to_string())
                .unwrap_or_else(|| raw.trim().chars().take(300).collect());
            Err(OAuthError {
                message: description,
                code,
            })
        }
        Err(_) => Err(OAuthError {
            message: format!("HTTP {status} from {url}: {}", raw.trim().chars().take(300).collect::<String>()),
            code: None,
        }),
    }
}

// --------------------------------------------------------------------------
// Token cache
// --------------------------------------------------------------------------

fn cache_path() -> std::path::PathBuf {
    token_cache_path()
}

pub fn load_cache() -> Value {
    let Ok(raw) = std::fs::read_to_string(cache_path()) else {
        return json!({});
    };
    match serde_json::from_str::<Value>(&raw) {
        Ok(v) if v.is_object() => v,
        _ => json!({}),
    }
}

/// Write the cache atomically at mode 0600, in a 0700 directory.
pub fn save_cache(data: &Value) -> Result<()> {
    ensure_config_dir();
    let path = cache_path();
    let text = serde_json::to_string_pretty(data)
        .map_err(|e| freepod(format!("cannot serialize token cache: {e}")))?;
    let text = format!("{text}\n");
    let pid = std::process::id();
    let temporary = path.with_file_name(format!("tokens.json.{pid}.tmp"));
    // Create the temp file owner-only before anything is written into it.
    use std::io::Write;
    let mut options = std::fs::OpenOptions::new();
    options.create_new(true);
    options.write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&temporary)
        .map_err(|e| freepod(format!("cannot create token cache: {e}")))?;
    file.write_all(text.as_bytes())
        .map_err(|e| freepod(format!("cannot write token cache: {e}")))?;
    drop(file);
    std::fs::rename(&temporary, &path)
        .map_err(|e| {
            let _ = std::fs::remove_file(&temporary);
            freepod(format!("cannot write token cache: {e}"))
        })?;
    // Assert the mode on the final path too, in case it pre-existed.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
    }
    Ok(())
}

pub fn load_refresh_token(env: &str) -> Option<String> {
    let data = load_cache();
    let token = data
        .get("environments")?
        .get(env)?
        .get("refresh_token")?
        .as_str()?
        .to_string();
    if token.is_empty() {
        None
    } else {
        Some(token)
    }
}

pub fn store_refresh_token(env: &str, client_id: &str, refresh_token: Option<&str>) {
    let Some(refresh_token) = refresh_token.filter(|t| !t.is_empty()) else {
        return;
    };
    let mut data = load_cache();
    let obj = data.as_object_mut().unwrap();
    let environments = obj
        .entry("environments")
        .or_insert_with(|| json!({}))
        .as_object_mut()
        .unwrap();
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    environments.insert(
        env.to_string(),
        json!({
            "client_id": client_id,
            "refresh_token": refresh_token,
            "stored_at": now,
        }),
    );
    obj.insert("version".to_string(), json!(CACHE_VERSION));
    let _ = save_cache(&data);
}

/// Drop one environment's cached credential. Others are untouched.
pub fn forget_environment(env: &str) -> bool {
    let mut data = load_cache();
    let Some(obj) = data.as_object_mut() else {
        return false;
    };
    let Some(environments) = obj.get_mut("environments").and_then(|v| v.as_object_mut()) else {
        return false;
    };
    if !environments.contains_key(env) {
        return false;
    }
    environments.remove(env);
    let _ = save_cache(&data);
    true
}

// --------------------------------------------------------------------------
// Flow selection
// --------------------------------------------------------------------------

/// Decide whether a browser on *this* machine can serve a loopback redirect.
pub fn detect_browser() -> (bool, String) {
    if std::path::Path::new("/.dockerenv").exists() {
        return (false, "running in a container (/.dockerenv present)".to_string());
    }
    if let Ok(cgroup) = std::fs::read_to_string("/proc/1/cgroup") {
        if ["docker", "containerd", "kubepods", "libpod"]
            .iter()
            .any(|m| cgroup.contains(m))
        {
            return (
                false,
                "running in a container (container runtime in /proc/1/cgroup)".to_string(),
            );
        }
    }
    #[cfg(target_os = "linux")]
    {
        let has_display = ["DISPLAY", "WAYLAND_DISPLAY", "BROWSER"]
            .iter()
            .any(|name| std::env::var(name).map(|v| !v.is_empty()).unwrap_or(false));
        if !has_display {
            return (
                false,
                "no DISPLAY, WAYLAND_DISPLAY or BROWSER set on Linux".to_string(),
            );
        }
    }
    let browser = webbrowser::Browser::default();
    (true, format!("browser available ({browser:?})"))
}

// --------------------------------------------------------------------------
// Flow (a): authorization code + PKCE over a loopback listener
// --------------------------------------------------------------------------

/// Handle a single HTTP request on the loopback listener. Returns the query
/// params if it was the callback, else None.
fn handle_one_request(stream: &mut std::net::TcpStream) -> std::io::Result<Option<HashMap<String, String>>> {
    let mut buf = [0u8; 8192];
    let mut data: Vec<u8> = Vec::new();
    // Read until end of headers.
    loop {
        let n = stream.read(&mut buf)?;
        if n == 0 {
            break;
        }
        data.extend_from_slice(&buf[..n]);
        if data.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
        if data.len() > 65536 {
            break;
        }
    }
    let head = String::from_utf8_lossy(&data);
    let first_line = head.lines().next().unwrap_or("");
    let mut parts = first_line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("");

    let (path, query) = match target.find('?') {
        Some(idx) => (&target[..idx], &target[idx + 1..]),
        None => (target, ""),
    };

    let is_callback = method == "GET" && path == CALLBACK_PATH;
    let params: HashMap<String, String> = if is_callback {
        url::form_urlencoded::parse(query.as_bytes())
            .into_owned()
            .collect()
    } else {
        HashMap::new()
    };

    let (title, detail) = if is_callback && params.contains_key("error") {
        ("Authorization failed", params.get("error_description").or_else(|| params.get("error")).cloned().unwrap_or_default())
    } else if is_callback {
        (
            "Signed in to Freepod",
            "You can close this tab and return to your terminal.".to_string(),
        )
    } else {
        ("Not found", "Not the callback".to_string())
    };

    let status = if is_callback { "200 OK" } else { "404 Not Found" };
    let page = format!(
        "<!doctype html><meta charset='utf-8'><title>Freepod CLI</title>\
         <body style=\"font-family:system-ui,sans-serif;margin:4rem auto;max-width:32rem\">\
         <h1 style='font-size:1.25rem'>{title}</h1><p>{detail}</p></body>"
    );
    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\n\
         Content-Length: {}\r\nConnection: close\r\n\r\n{page}",
        page.len()
    );
    use std::io::Write;
    stream.write_all(response.as_bytes())?;
    stream.flush()?;

    if is_callback {
        Ok(Some(params))
    } else {
        Ok(None)
    }
}

/// Run the loopback flow: bind, open the browser, wait for the redirect, and
/// exchange the code for tokens.
pub async fn loopback_flow(
    client: &reqwest::Client,
    env: &Environment,
    timeout: u64,
    verbose: bool,
) -> Result<Value> {
    let (verifier, challenge) = pkce_pair();
    let mut state_bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut state_bytes);
    let state = hex::encode(state_bytes);

    let listener = TcpListener::bind((CALLBACK_HOST, 0))
        .map_err(|e| freepod(format!("cannot bind loopback listener: {e}")))?;
    let port = listener
        .local_addr()
        .map_err(|e| freepod(format!("cannot read listener address: {e}")))?
        .port();
    let redirect_uri = format!("http://{CALLBACK_HOST}:{port}{CALLBACK_PATH}");

    let authorization_url = format!(
        "{}?{}",
        env.authorization_endpoint(),
        query_pairs(&[
            ("client_id", env.client_id),
            ("response_type", "code"),
            ("redirect_uri", redirect_uri.as_str()),
            ("scope", SCOPES),
            ("state", state.as_str()),
            ("code_challenge", challenge.as_str()),
            ("code_challenge_method", "S256"),
        ])
    );

    log(&format!("Listening on {redirect_uri} for the authorization redirect."));
    if verbose {
        log(&format!("Authorization URL: {authorization_url}"));
    }

    if webbrowser::open(&authorization_url).is_ok() {
        log("Opened your browser to sign in.");
    } else {
        log(&format!("Could not open a browser automatically. Visit this URL:\n  {authorization_url}"));
    }

    let deadline = Instant::now() + Duration::from_secs(timeout);
    let params = loop {
        if Instant::now() >= deadline {
            return Err(freepod(format!(
                "timed out after {timeout}s waiting for the authorization redirect \
                 (use --device for a browser-less flow)"
            )));
        }
        match listener.accept() {
            Ok((mut stream, _)) => {
                let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
                match handle_one_request(&mut stream) {
                    Ok(Some(p)) => break p,
                    Ok(None) => continue,
                    Err(e) => {
                        return Err(freepod(format!("loopback listener error: {e}")));
                    }
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(100));
            }
            Err(e) => return Err(freepod(format!("loopback listener error: {e}"))),
        }
    };
    // Note: listener dropped here.

    if let Some(error) = params.get("error") {
        return Err(freepod(params
            .get("error_description")
            .cloned()
            .unwrap_or_else(|| error.clone())));
    }
    if params.get("state").map(|s| s.as_str()) != Some(state.as_str()) {
        return Err(freepod(
            "state mismatch on the authorization redirect — possible CSRF, refusing the response",
        ));
    }
    let Some(code) = params.get("code") else {
        return Err(freepod("authorization redirect carried no code".to_string()));
    };

    log("Received the authorization code; exchanging it for tokens.");
    let mut fields = HashMap::new();
    fields.insert("grant_type".to_string(), "authorization_code".to_string());
    fields.insert("client_id".to_string(), env.client_id.to_string());
    fields.insert("code".to_string(), code.clone());
    fields.insert("redirect_uri".to_string(), redirect_uri);
    fields.insert("code_verifier".to_string(), verifier);
    post_form(client, &env.token_endpoint(), &fields)
        .await
        .map_err(|e| freepod(e.message))
}

// --------------------------------------------------------------------------
// Flow (b): device authorization grant
// --------------------------------------------------------------------------

pub async fn device_flow(
    client: &reqwest::Client,
    env: &Environment,
    verbose: bool,
) -> Result<Value> {
    let (verifier, challenge) = pkce_pair();

    let mut fields = HashMap::new();
    fields.insert("client_id".to_string(), env.client_id.to_string());
    fields.insert("scope".to_string(), SCOPES.to_string());
    fields.insert("code_challenge".to_string(), challenge);
    fields.insert("code_challenge_method".to_string(), "S256".to_string());
    let authorization = post_form(client, &env.device_endpoint(), &fields)
        .await
        .map_err(|e| freepod(e.message))?;

    let device_code = authorization.get("device_code").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let user_code = authorization.get("user_code").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let interval = authorization.get("interval").and_then(|v| v.as_u64()).unwrap_or(1);
    let expires_in = authorization.get("expires_in").and_then(|v| v.as_u64()).unwrap_or(600);
    let verification_uri = authorization.get("verification_uri").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let complete_uri = authorization.get("verification_uri_complete").and_then(|v| v.as_str()).map(|s| s.to_string());

    log("\nTo sign in, open this URL in any browser — on this machine or another:\n");
    if let Some(complete_uri) = &complete_uri {
        log(&format!("    {complete_uri}\n"));
        log(&format!("  That link already carries the code {user_code}, so Keycloak will"));
        log("  not ask you for it. To type it in by hand instead, open");
        log(&format!("  {verification_uri} and enter {user_code}\n"));
    } else {
        log(&format!("    {verification_uri}\n"));
        log(&format!("  and enter the code:  {user_code}\n"));
    }
    log(&format!("Waiting up to {expires_in}s for approval (polling every {interval}s)..."));

    let deadline = Instant::now() + Duration::from_secs(expires_in);
    let mut interval = interval;
    loop {
        tokio::time::sleep(Duration::from_secs(interval)).await;
        if Instant::now() >= deadline {
            return Err(freepod(format!(
                "device code expired after {expires_in}s without approval"
            )));
        }

        let mut poll_fields = HashMap::new();
        poll_fields.insert("grant_type".to_string(), crate::config::DEVICE_GRANT.to_string());
        poll_fields.insert("client_id".to_string(), env.client_id.to_string());
        poll_fields.insert("device_code".to_string(), device_code.clone());
        poll_fields.insert("code_verifier".to_string(), verifier.clone());

        match post_form(client, &env.token_endpoint(), &poll_fields).await {
            Ok(tokens) => {
                log("Approved.");
                return Ok(tokens);
            }
            Err(e) => match e.code.as_deref() {
                Some("authorization_pending") => {
                    if verbose {
                        log("  ...still pending");
                    }
                    continue;
                }
                Some("slow_down") => {
                    interval += 5;
                    log(&format!("  ...server asked us to slow down; polling every {interval}s"));
                    continue;
                }
                Some("expired_token") => {
                    return Err(freepod(
                        "the device code expired before it was approved — rerun to get a new one",
                    ));
                }
                Some("access_denied") => {
                    return Err(freepod("authorization was denied in the browser".to_string()));
                }
                _ => return Err(freepod(e.message)),
            },
        }
    }
}

// --------------------------------------------------------------------------
// Session
// --------------------------------------------------------------------------

/// Holds the credential for one environment and knows how to renew it.
#[derive(Clone)]
pub struct Session {
    pub env: Environment,
    pub timeout: u64,
    pub force_flow: Option<String>,
    pub verbose: bool,
    pub access_token: Option<String>,
    pub refresh_token: Option<String>,
    pub credential_source: String,
    pub flow_used: Option<String>,
}

impl Session {
    pub fn new(
        env: Environment,
        timeout: u64,
        force_flow: Option<String>,
        verbose: bool,
    ) -> Self {
        Self {
            env,
            timeout,
            force_flow,
            verbose,
            access_token: None,
            refresh_token: None,
            credential_source: "none".to_string(),
            flow_used: None,
        }
    }

    /// Reuse a cached refresh token when possible, else run a full login.
    pub async fn authenticate(
        &mut self,
        client: &reqwest::Client,
        force_login: bool,
        interactive: bool,
    ) -> Result<()> {
        if !force_login {
            if let Some(cached) = load_refresh_token(self.env.name) {
                if self.verbose {
                    log(&format!(
                        "Found a cached refresh token for '{}'; refreshing.",
                        self.env.name
                    ));
                }
                self.refresh_token = Some(cached.clone());
                if self.refresh(client).await {
                    self.credential_source = "cached refresh token".to_string();
                    return Ok(());
                }
                if !interactive {
                    return Err(authentication(format!(
                        "the cached credential for '{}' is no longer valid — \
                         run `freepod --env {} login`",
                        self.env.name, self.env.name
                    )));
                }
                log("Refresh failed; falling back to a full login.");
            } else if !interactive {
                return Err(authentication(format!(
                    "not authenticated for '{}' — run `freepod --env {} login`",
                    self.env.name, self.env.name
                )));
            } else {
                log(&format!("No cached credential for '{}'.", self.env.name));
            }
        }
        self.login(client).await?;
        self.credential_source = "fresh login".to_string();
        Ok(())
    }

    pub async fn login(&mut self, client: &reqwest::Client) -> Result<()> {
        let (flow, reason) = self.choose_flow();
        log(&format!("Using the {flow} flow — {reason}."));
        self.flow_used = Some(flow.clone());

        let tokens = if flow == "loopback" {
            loopback_flow(client, &self.env, self.timeout, self.verbose).await?
        } else {
            device_flow(client, &self.env, self.verbose).await?
        };
        self.apply(tokens);
        Ok(())
    }

    fn choose_flow(&self) -> (String, String) {
        match self.force_flow.as_deref() {
            Some("loopback") => ("loopback".to_string(), "forced with --loopback".to_string()),
            Some("device") => ("device".to_string(), "forced with --device".to_string()),
            _ => {
                let (usable, reason) = detect_browser();
                if usable {
                    ("loopback".to_string(), reason)
                } else {
                    ("device".to_string(), reason)
                }
            }
        }
    }

    /// Exchange the refresh token for a new access token. False on failure.
    pub async fn refresh(&mut self, client: &reqwest::Client) -> bool {
        let Some(refresh_token) = self.refresh_token.clone() else {
            return false;
        };
        let mut fields = HashMap::new();
        fields.insert("grant_type".to_string(), "refresh_token".to_string());
        fields.insert("client_id".to_string(), self.env.client_id.to_string());
        fields.insert("refresh_token".to_string(), refresh_token);
        match post_form(client, &self.env.token_endpoint(), &fields).await {
            Ok(tokens) => {
                self.apply(tokens);
                true
            }
            Err(e) => {
                if self.verbose {
                    log(&format!("Refresh rejected: {}", e.message));
                }
                false
            }
        }
    }

    fn apply(&mut self, tokens: Value) {
        self.access_token = tokens.get("access_token").and_then(|v| v.as_str()).map(|s| s.to_string());
        // revokeRefreshToken is false on this realm, so a refresh response may
        // omit a new refresh token; keep the one we already hold in that case.
        self.refresh_token = tokens
            .get("refresh_token")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string())
            .or_else(|| self.refresh_token.clone());
        if let Some(rt) = &self.refresh_token {
            store_refresh_token(self.env.name, self.env.client_id, Some(rt));
        }
    }
}
