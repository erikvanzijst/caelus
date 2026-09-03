//! The REST client and the platform's HTTP contract.
//!
//! Wraps `reqwest` and enforces the same status semantics the Python client
//! did in `api.py`: 401 stops and explains (never re-authenticates), 403
//! refreshes the token once and retries, 404 with a "Not authenticated"
//! detail is a platform condition, and safe methods retry on 5xx/network
//! errors. Mirrors `api.py`.
//!
//! Like the Python client, a non-streaming `request` hands back a response
//! whose body is already in memory; only `stream_request` yields one whose
//! body is still arriving.

use std::time::Duration;

use percent_encoding::{AsciiSet, NON_ALPHANUMERIC};
use serde_json::Value;

use crate::auth::Session;
use crate::config::{Environment, USER_AGENT};
use crate::errors::{authentication, freepod, permission, Result};

/// Base delay for the backoff between safe-method retries; doubles each time.
const BACKOFF_BASE: f64 = 0.5;

/// Max attempts for safe methods (GET/HEAD/OPTIONS) on 5xx/network errors.
const SAFE_ATTEMPTS: u32 = 3;

/// Percent-encode a path segment the way `quote(value, safe='')` does:
/// everything except the unreserved characters.
pub(crate) fn encode_segment(value: &str) -> String {
    const ENCODE: &AsciiSet = &NON_ALPHANUMERIC
        .remove(b'_')
        .remove(b'.')
        .remove(b'-')
        .remove(b'~');
    percent_encoding::percent_encode(value.as_bytes(), ENCODE).to_string()
}

/// A shared HTTP client: a 15s connect timeout, no global per-request timeout
/// (each request sets its own; the log stream sets none and bounds reads itself).
pub fn http_client() -> reqwest::Client {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(15))
        .build()
        .expect("failed to build http client")
}

/// The `detail` string of a JSON error body, or None.
pub fn detail_of(body: &str) -> Option<String> {
    serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|v| v.get("detail").and_then(|d| d.as_str()).map(|s| s.to_string()))
}

/// A completed, buffered response — the body is fully in memory.
#[derive(Debug, Clone)]
pub struct ApiResponse {
    pub status: u16,
    pub url: String,
    pub body: Vec<u8>,
    pub headers: reqwest::header::HeaderMap,
}

impl ApiResponse {
    pub fn is_success(&self) -> bool {
        self.status < 400
    }

    /// A response header's value, if present and valid UTF-8.
    pub fn header(&self, name: &str) -> Option<String> {
        self.headers
            .get(name)
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string())
    }

    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).to_string()
    }

    /// The `detail` of a JSON error body, if the body is one.
    pub fn detail(&self) -> Option<String> {
        detail_of(&self.text())
    }

    /// Decode a 2xx body as JSON; on 4xx/5xx, raise with the detail.
    pub fn decode(&self) -> Result<Value> {
        if !self.is_success() {
            let body = self
                .detail()
                .unwrap_or_else(|| self.text().trim().chars().take(300).collect());
            return Err(freepod(format!("HTTP {} from {}: {}", self.status, self.url, body)));
        }
        serde_json::from_slice(&self.body)
            .map_err(|_| freepod(format!("unparseable response from {}", self.url)))
    }
}

/// The outcome of a streaming request.
pub enum StreamOutcome {
    /// A 2xx stream; the body is still arriving.
    Live(reqwest::Response),
    /// A non-success the contract does not claim, with its detail.
    Refused { status: u16, detail: String },
}

/// The API client for one environment and one authenticated session.
pub struct ApiClient {
    pub env: Environment,
    pub session: Session,
    pub timeout: u64,
    client: reqwest::Client,
}

impl ApiClient {
    /// Build over a caller-supplied client, so the session and the API share
    /// one connection pool.
    pub fn with_client(
        env: Environment,
        session: Session,
        timeout: u64,
        client: reqwest::Client,
    ) -> Self {
        Self {
            env,
            session,
            timeout,
            client,
        }
    }

    /// A shared handle to the underlying HTTP client, so a caller can build a
    /// sibling client (the hostname checker) that shares the connection pool.
    pub fn client(&self) -> &reqwest::Client {
        &self.client
    }

    fn base_headers(&self) -> Vec<(String, String)> {
        let mut headers = vec![
            ("Accept".to_string(), "application/json".to_string()),
            ("User-Agent".to_string(), USER_AGENT.to_string()),
        ];
        if let Some(token) = &self.session.access_token {
            headers.push(("Authorization".to_string(), format!("Bearer {token}")));
        }
        headers
    }

    /// One HTTP attempt; no retries, no contract.
    async fn do_request(
        &self,
        method: &str,
        url: &str,
        params: Option<&[(String, String)]>,
        json: Option<&Value>,
        extra_headers: Option<&[(String, String)]>,
        total_timeout: Option<u64>,
    ) -> std::result::Result<reqwest::Response, reqwest::Error> {
        let m = reqwest::Method::from_bytes(method.as_bytes())
            .unwrap_or(reqwest::Method::GET);
        let mut req = self.client.request(m, url);
        if let Some(p) = params {
            req = req.query(p);
        }
        if let Some(j) = json {
            req = req.json(j);
        }
        for (k, v) in self.base_headers() {
            req = req.header(k.as_str(), v.as_str());
        }
        if let Some(h) = extra_headers {
            for (k, v) in h {
                req = req.header(k.as_str(), v.as_str());
            }
        }
        if let Some(secs) = total_timeout {
            req = req.timeout(Duration::from_secs(secs));
        }
        req.send().await
    }

    /// Send with the retry policy: safe methods retry on 5xx/network errors.
    /// Returns the live response (body not yet read).
    async fn send(
        &self,
        method: &str,
        url: &str,
        params: Option<&[(String, String)]>,
        json: Option<&Value>,
        extra_headers: Option<&[(String, String)]>,
    ) -> Result<reqwest::Response> {
        let safe = matches!(
            method.to_uppercase().as_str(),
            "GET" | "HEAD" | "OPTIONS"
        );
        let attempts = if safe { SAFE_ATTEMPTS } else { 1 };
        let mut last_error = String::new();
        for attempt in 1..=attempts {
            match self
                .do_request(method, url, params, json, extra_headers, Some(self.timeout))
                .await
            {
                Err(e) => {
                    last_error = e.to_string();
                    if attempt >= attempts {
                        return Err(freepod(format!("cannot reach {url}: {e}")));
                    }
                    self.backoff(attempt).await;
                }
                Ok(response) => {
                    if response.status().is_server_error() && attempt < attempts {
                        self.backoff(attempt).await;
                        continue;
                    }
                    return Ok(response);
                }
            }
        }
        Err(freepod(format!("cannot reach {url}: {last_error}")))
    }

    async fn backoff(&self, attempt: u32) {
        let delay = BACKOFF_BASE * 2f64.powi((attempt - 1) as i32);
        if delay > 0.0 {
            tokio::time::sleep(Duration::from_secs_f64(delay)).await;
        }
    }

    /// Refresh the token if it is stale, else log in from scratch.
    async fn renew(&mut self) -> Result<()> {
        if self.session.refresh(&self.client).await {
            self.session.credential_source = "refreshed token".to_string();
            return Ok(());
        }
        self.session.login(&self.client).await?;
        self.session.credential_source = "fresh login (after failed refresh)".to_string();
        Ok(())
    }

    /// One request through the platform's contract. Returns the buffered
    /// response for any status the contract does not claim (including 4xx like
    /// 409 or a plain 404, which callers inspect). Raises for credential
    /// statuses.
    pub async fn request(
        &mut self,
        method: &str,
        path: &str,
        params: Option<&[(String, String)]>,
        json: Option<&Value>,
        extra_headers: Option<&[(String, String)]>,
    ) -> Result<ApiResponse> {
        let url = self.env.url(path);
        let mut refreshed = false;
        loop {
            let response = self.send(method, &url, params, json, extra_headers).await?;
            let status = response.status().as_u16();
            if status == 401 {
                return Err(authentication(self.unauthenticated_message(&url)));
            }
            if status == 403 {
                let detail = detail_of(&response.text().await.unwrap_or_default());
                if let Some(detail) = detail {
                    return Err(permission(format!("403 from {url} — {detail}")));
                }
                if refreshed {
                    return Err(permission(format!(
                        "403 from {url} even after refreshing — the token is still not \
                         verifiable. Run `freepod login --env {}` to re-authenticate \
                         from scratch.",
                        self.env.name
                    )));
                }
                refreshed = true;
                self.renew().await?;
                continue;
            }
            let headers = response.headers().clone();
            let body = response
                .bytes()
                .await
                .map_err(|e| freepod(format!("cannot read response from {url}: {e}")))?;
            let resp = ApiResponse {
                status,
                url: url.clone(),
                body: body.to_vec(),
                headers,
            };
            if status == 404 && resp.detail().as_deref() == Some("Not authenticated") {
                return Err(freepod(format!(
                    "404 'Not authenticated' from {url} — no identity reached the API. \
                     This is an unexpected platform condition, not a credential problem; \
                     please report it."
                )));
            }
            return Ok(resp);
        }
    }

    /// A streaming request (SSE logs): the contract, but no retries and no
    /// total timeout — the caller bounds each read.
    ///
    /// A success yields the live response whose body is still arriving; a
    /// non-success the contract does not claim (503, a plain 404, ...) comes
    /// back as `Refused` with its detail, because the body must be pulled to
    /// read it and a stream cannot be handed back half-consumed.
    pub async fn stream_request(
        &mut self,
        path: &str,
        params: Option<&[(String, String)]>,
    ) -> Result<StreamOutcome> {
        let url = self.env.url(path);
        let mut refreshed = false;
        loop {
            let response = self
                .do_request("GET", &url, params, None, None, None)
                .await
                .map_err(|e| freepod(format!("cannot reach {url}: {e}")))?;
            let status = response.status().as_u16();
            if status == 401 {
                return Err(authentication(self.unauthenticated_message(&url)));
            }
            if status == 403 {
                let detail = detail_of(&response.text().await.unwrap_or_default());
                if let Some(detail) = detail {
                    return Err(permission(format!("403 from {url} — {detail}")));
                }
                if refreshed {
                    return Err(permission(format!(
                        "403 from {url} even after refreshing — the token is still not \
                         verifiable. Run `freepod login --env {}` to re-authenticate.",
                        self.env.name
                    )));
                }
                refreshed = true;
                self.renew().await?;
                continue;
            }
            if status < 400 {
                return Ok(StreamOutcome::Live(response));
            }
            // Non-success: pull the body to identify the platform's 404 and to
            // hand the detail to the caller.
            let body = response.text().await.unwrap_or_default();
            let detail = detail_of(&body);
            if status == 404 && detail.as_deref() == Some("Not authenticated") {
                return Err(freepod(format!(
                    "404 'Not authenticated' from {url} — no identity reached the API. \
                     This is an unexpected platform condition, not a credential problem; \
                     please report it."
                )));
            }
            let detail = detail
                .unwrap_or_else(|| body.trim().chars().take(300).collect());
            return Ok(StreamOutcome::Refused { status, detail });
        }
    }

    fn unauthenticated_message(&self, url: &str) -> String {
        match self.env.requires_group() {
            Some(group) => format!(
                "401 from {url} — no credential, or your account lacks access to \
                 '{}'.\n  {} requires membership of the '{}' Keycloak group.\n  \
                 Re-authenticating will succeed and change nothing — check the group \
                 membership first.",
                self.env.name, self.env.api_base, group
            ),
            None => format!(
                "401 from {url} — no credential reached the API.\n  \
                 Run `freepod login --env {}` to authenticate.",
                self.env.name
            ),
        }
    }

    // Convenience verbs.

    pub async fn get(
        &mut self,
        path: &str,
        params: Option<&[(String, String)]>,
    ) -> Result<ApiResponse> {
        self.request("GET", path, params, None, None).await
    }

    pub async fn get_json(
        &mut self,
        path: &str,
        params: Option<&[(String, String)]>,
    ) -> Result<Value> {
        self.get(path, params).await?.decode()
    }

    pub async fn post_json(&mut self, path: &str, json: Option<&Value>) -> Result<ApiResponse> {
        self.request("POST", path, None, json, None).await
    }

    pub async fn put_json(&mut self, path: &str, json: Option<&Value>) -> Result<ApiResponse> {
        self.request("PUT", path, None, json, None).await
    }

    pub async fn delete(&mut self, path: &str) -> Result<ApiResponse> {
        self.request("DELETE", path, None, None, None).await
    }

    // Domain helpers.

    /// `GET /api/me`; the session's identity.
    pub async fn me(&mut self) -> Result<Value> {
        let body = self.get_json("/api/me", None).await?;
        if !body.is_object() || body.get("id").is_none() {
            return Err(freepod(format!("unexpected /api/me response: {body}")));
        }
        Ok(body)
    }

    /// `GET /api/products` — the full catalog.
    pub async fn products(&mut self) -> Result<Vec<Value>> {
        let body = self.get_json("/api/products", None).await?;
        let arr = body
            .as_array()
            .ok_or_else(|| freepod(format!("unexpected /api/products response: {body}")))?;
        Ok(arr.clone())
    }

    /// The product with a given slug, if any.
    pub async fn find_product(&mut self, slug: &str) -> Result<Option<Value>> {
        for product in self.products().await? {
            if product.get("slug").and_then(|v| v.as_str()) == Some(slug) {
                return Ok(Some(product));
            }
        }
        Ok(None)
    }

    /// `GET /api/domains` — the platform's base domains.
    pub async fn domains(&mut self) -> Result<Vec<String>> {
        let body = self.get_json("/api/domains", None).await?;
        let arr = body
            .as_array()
            .ok_or_else(|| freepod(format!("unexpected /api/domains response: {body}")))?;
        Ok(arr
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect())
    }

    /// `GET /api/hostnames/{fqdn}` — a hostname usability verdict.
    pub async fn check_hostname(&mut self, fqdn: &str) -> Result<Value> {
        let path = format!("/api/hostnames/{}", encode_segment(fqdn));
        let body = self.get_json(&path, None).await?;
        if !body.is_object() {
            return Err(freepod(format!("unexpected hostname check response: {body}")));
        }
        Ok(body)
    }

    /// `GET /api/ssh` — this environment's edge address and host key.
    pub async fn ssh_edge(&mut self) -> Result<Value> {
        let body = self.get_json("/api/ssh", None).await?;
        if !body.is_object() {
            return Err(freepod(format!("unexpected /api/ssh response: {body}")));
        }
        Ok(body)
    }
}
