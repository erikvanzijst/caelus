//! Schema-driven prompting, and hostname normalization.
//!
//! Walks the product template's `values_schema_json`, prompts for each
//! `required` property, and validates answers locally before they reach the
//! API. Shared by `init` and `deploy`. Mirrors `values.py`.

use std::collections::HashMap;
use std::sync::Arc;

use regex::Regex;
use serde_json::Value;

use crate::api::encode_segment;
use crate::config::USER_AGENT;
use crate::errors::{freepod, Result};
use crate::prompt;

/// The schema title that marks the hostname property, matched case-insensitively.
pub const HOSTNAME_TITLE: &str = "hostname";

/// `GET /api/hostnames/{fqdn}` answers 200 with `{fqdn, usable, reason}`.
pub fn hostname_reasons() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();
    m.insert("invalid", "that is not a valid hostname");
    m.insert(
        "nested_subdomain",
        "nested subdomains are not allowed on a platform domain",
    );
    m.insert("reserved", "that name is reserved by the platform");
    m.insert("in_use", "that name is already taken by another deployment");
    m.insert(
        "not_resolving",
        "that name does not have a CNAME pointing at the platform yet — \
         custom domains need the DNS record in place first",
    );
    m
}

pub fn describe_reason(reason: Option<&str>) -> String {
    let Some(reason) = reason.filter(|r| !r.is_empty()) else {
        return "the platform reported it as unusable".to_string();
    };
    hostname_reasons()
        .get(reason)
        .map(|s| s.to_string())
        .unwrap_or_else(|| format!("the platform reported '{reason}'"))
}

/// A hostname usability check, performed by the API.
#[async_trait::async_trait]
pub trait HostnameChecker: Send + Sync {
    async fn check(&self, fqdn: &str) -> Result<Value>;
}

/// Return a human explanation of the first violated constraint, or None.
///
/// Only the constraints that can be evaluated without the platform are
/// checked. Everything else is left to the API, which is the authority.
pub fn check_constraints(name: &str, value: &str, spec: &Value) -> Option<String> {
    if let Some(enum_) = spec.get("enum").and_then(|v| v.as_array()) {
        if !enum_.is_empty() {
            let allowed: Vec<String> = enum_.iter().map(|v| v.to_string()).collect();
            let in_enum = enum_.iter().any(|v| v.as_str() == Some(value));
            if !in_enum {
                return Some(format!("{name} must be one of: {}", allowed.join(", ")));
            }
            return None;
        }
    }

    if let Some(minimum) = spec.get("minLength").and_then(|v| v.as_u64()) {
        let min = minimum as usize;
        if value.chars().count() < min {
            return Some(format!(
                "{name} must be at least {min} character{}",
                if min == 1 { "" } else { "s" }
            ));
        }
    }

    if let Some(maximum) = spec.get("maxLength").and_then(|v| v.as_u64()) {
        let max = maximum as usize;
        let len = value.chars().count();
        if len > max {
            return Some(format!("{name} must be at most {max} characters (that was {len})"));
        }
    }

    if let Some(pattern) = spec.get("pattern").and_then(|v| v.as_str()).filter(|p| !p.is_empty()) {
        // An un-compilable pattern is the platform's problem, not the user's;
        // let the API judge rather than blocking on it here.
        if let Ok(re) = Regex::new(pattern) {
            if !re.is_match(value) {
                return Some(format!("{name} must match the pattern {pattern}"));
            }
        }
    }

    None
}

/// Whether a schema property is the hostname.
pub fn is_hostname_property(spec: &Value) -> bool {
    spec.get("title")
        .and_then(|v| v.as_str())
        .map(|t| t.trim().eq_ignore_ascii_case(HOSTNAME_TITLE))
        .unwrap_or(false)
}

/// Lowercase, and complete a bare label with the first platform domain.
pub fn normalize_hostname(value: &str, domains: &[String]) -> String {
    let candidate = value.trim().to_lowercase();
    let candidate = candidate.trim_end_matches('.').to_string();
    if candidate.is_empty() {
        return candidate;
    }
    if !candidate.contains('.') {
        if let Some(first) = domains.first() {
            return format!("{candidate}.{first}");
        }
    }
    candidate
}

/// Collects the values a template's schema requires.
pub struct ValueCollector {
    schema: Value,
    domains: Vec<String>,
    checker: Option<Arc<dyn HostnameChecker>>,
    interactive: bool,
}

impl ValueCollector {
    pub fn new(
        schema: Value,
        domains: Vec<String>,
        checker: Option<Arc<dyn HostnameChecker>>,
        interactive: bool,
    ) -> Self {
        Self {
            schema,
            domains,
            checker,
            interactive,
        }
    }

    fn properties(&self) -> Option<&serde_json::Map<String, Value>> {
        self.schema
            .get("properties")
            .and_then(|v| v.as_object())
    }

    fn required(&self) -> Vec<String> {
        self.schema
            .get("required")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default()
    }

    fn spec_for(&self, name: &str) -> Value {
        self.properties()
            .and_then(|p| p.get(name))
            .cloned()
            .unwrap_or(Value::Object(Default::default()))
    }

    /// Return the required values, prompting for whatever is not settled.
    pub async fn collect(
        &self,
        existing: &HashMap<String, Value>,
        only_missing: bool,
    ) -> Result<HashMap<String, Value>> {
        let mut result: HashMap<String, Value> = HashMap::new();

        for name in self.required() {
            let spec = self.spec_for(&name);
            let present = existing.get(&name);
            let has_value = present
                .and_then(|v| v.as_str())
                .map(|s| !s.is_empty())
                .unwrap_or(false);

            if has_value && only_missing {
                result.insert(name.clone(), present.unwrap().clone());
                continue;
            }
            let current = if has_value {
                present.and_then(|v| v.as_str()).map(|s| s.to_string())
            } else {
                None
            };
            let resolved = self.resolve(&name, &spec, current.as_deref()).await?;
            result.insert(name.clone(), Value::String(resolved));
        }

        // Carry through any non-required value the user already had.
        for (name, value) in existing {
            result.entry(name.clone()).or_insert_with(|| value.clone());
        }

        Ok(result)
    }

    async fn resolve(&self, name: &str, spec: &Value, current: Option<&str>) -> Result<String> {
        let hostname = is_hostname_property(spec);

        if let Some(current) = current {
            if !self.interactive {
                return self.validate_noninteractive(name, spec, current, hostname);
            }
        } else if !self.interactive {
            return Err(freepod(format!(
                "'{name}' is required by the product template and is not set, and \
                 there is no terminal to ask on. Set it in .freepod-rust.json and re-run."
            )));
        }

        self.introduce(name, spec);
        self.prompt_loop(name, spec, current, hostname).await
    }

    fn introduce(&self, name: &str, spec: &Value) {
        if let Some(description) = spec.get("description").and_then(|v| v.as_str()) {
            let description = description.trim();
            if !description.is_empty() {
                eprintln!("{name}: {description}");
            }
        }
    }

    async fn prompt_loop(
        &self,
        name: &str,
        spec: &Value,
        current: Option<&str>,
        hostname: bool,
    ) -> Result<String> {
        let mut current = current.map(|s| s.to_string());
        loop {
            let answer = prompt::prompt_with_default(&format!("  {name}"), current.as_deref())?;
            let mut answer = answer.trim().to_string();

            if hostname {
                let normalized = normalize_hostname(&answer, &self.domains);
                if !normalized.is_empty()
                    && normalized != current.clone().unwrap_or_default()
                    && normalized.contains('.')
                {
                    eprintln!("  → {normalized}");
                }
                answer = normalized;
            }

            if let Some(problem) = check_constraints(name, &answer, spec) {
                eprintln!("  {problem}. Try again.");
                current = None;
                continue;
            }

            if hostname {
                if let Some(checker) = &self.checker {
                    let verdict = checker.check(&answer).await?;
                    let usable = verdict.get("usable").and_then(|v| v.as_bool()).unwrap_or(false);
                    if !usable {
                        let reason = verdict.get("reason").and_then(|v| v.as_str());
                        eprintln!(
                            "  {answer}: {}. Try again.",
                            describe_reason(reason)
                        );
                        current = None;
                        continue;
                    }
                }
            }

            return Ok(answer);
        }
    }

    fn validate_noninteractive(
        &self,
        name: &str,
        spec: &Value,
        value: &str,
        hostname: bool,
    ) -> Result<String> {
        let value = if hostname {
            normalize_hostname(value, &self.domains)
        } else {
            value.to_string()
        };
        if let Some(problem) = check_constraints(name, &value, spec) {
            return Err(freepod(format!("{problem} (currently {value:?})")));
        }
        Ok(value)
    }
}

/// Required property names absent or empty in `values`.
pub fn missing_required(schema: &Value, values: &HashMap<String, Value>) -> Vec<String> {
    let Some(required) = schema.get("required").and_then(|v| v.as_array()) else {
        return Vec::new();
    };
    let mut missing = Vec::new();
    for name in required.iter().filter_map(|v| v.as_str()) {
        let value = values.get(name);
        let empty = value.and_then(|v| v.as_str()).map(|s| s.is_empty()).unwrap_or(true);
        if empty {
            missing.push(name.to_string());
        }
    }
    missing
}

/// A hostname checker that asks the platform, `GET /api/hostnames/{fqdn}`.
///
/// The route is on the edge's anonymous list, so it needs no credential; the
/// client and environment are held separately from the `ApiClient` so the
/// checker can coexist with the calls a deploy makes around the prompts.
#[derive(Clone)]
pub struct ApiHostnameChecker {
    client: reqwest::Client,
    env: crate::config::Environment,
}

impl ApiHostnameChecker {
    pub fn new(client: reqwest::Client, env: crate::config::Environment) -> Self {
        Self { client, env }
    }
}

#[async_trait::async_trait]
impl HostnameChecker for ApiHostnameChecker {
    async fn check(&self, fqdn: &str) -> Result<Value> {
        let path = format!("/api/hostnames/{}", encode_segment(fqdn));
        let url = self.env.url(&path);
        let response = self
            .client
            .get(&url)
            .header("Accept", "application/json")
            .header("User-Agent", USER_AGENT)
            .send()
            .await
            .map_err(|e| freepod(format!("cannot reach {url}: {e}")))?;
        let body = response
            .text()
            .await
            .map_err(|e| freepod(format!("cannot read response from {url}: {e}")))?;
        let value: Value = serde_json::from_str(&body)
            .map_err(|_| freepod(format!("unparseable response from {url}")))?;
        if !value.is_object() {
            return Err(freepod(format!("unexpected hostname check response: {value}")));
        }
        Ok(value)
    }
}
