//! Terms of Service acceptance.
//!
//! The platform refuses to create a deployment for an account that has never
//! accepted the terms: `POST /api/users/{id}/deployments` answers **400** with
//! the detail `Terms of Service must be accepted before deploying`. That
//! refusal arrives at the very end of a deploy — after the archive has been
//! packed, uploaded, and built — so the client settles it in preflight
//! instead. Mirrors `tos.py`.
//!
//! Two things are deliberately separate:
//! - **The gate** is `version is not None`. The platform requires *some*
//!   acceptance, so checking it needs no idea which version is current.
//! - **Recording** an acceptance requires submitting the exact current version,
//!   or the platform answers 409. The client learns that version from
//!   `current_version` on the same document and never carries its own copy.
//!
//! Only a *create* is gated; an update of an existing deployment is not.

use serde_json::Value;

use crate::api::ApiClient;
use crate::config::Environment;
use crate::errors::{freepod, Result};

pub const ACCEPTANCE_PATH: &str = "/api/me/tos-acceptance";

/// The detail the platform's create refuses with when the terms are unaccepted.
pub const DEPLOY_REFUSAL: &str = "Terms of Service must be accepted before deploying";

/// The documents, in the order the web UI names them.
pub const DOCUMENTS: &[(&str, &str)] = &[
    ("Terms of Service", "terms"),
    ("Acceptable Use Policy", "aup"),
    ("Privacy Policy", "privacy"),
];

/// Verbatim from the web UI's deploy dialog.
pub const AGREEMENT: &str = "I agree to the Freepod Terms of Service and Acceptable Use Policy, and acknowledge the Privacy Policy.";

/// Why settling ended the way it did.
pub const ACCEPTED: &str = "accepted";
pub const DECLINED: &str = "declined";
pub const NO_TERMINAL: &str = "no-terminal";
pub const VERSION_UNKNOWN: &str = "version-unknown";

/// `GET /api/me/tos-acceptance` — always 200, even when nothing is accepted.
pub async fn read(api: &mut ApiClient) -> Result<Value> {
    let body = api.get_json(ACCEPTANCE_PATH, None).await?;
    if !body.is_object() {
        return Err(freepod(format!("unexpected {ACCEPTANCE_PATH} response: {body}")));
    }
    Ok(body)
}

/// Whether this account has accepted any version of the terms.
///
/// Python's `bool(record.get("version"))`: null and empty are "not accepted".
pub fn accepted(record: &Value) -> bool {
    match record.get("version") {
        None | Some(Value::Null) => false,
        Some(Value::String(s)) => !s.is_empty(),
        Some(_) => true,
    }
}

/// The version the platform currently requires, if it says.
pub fn current_version(record: &Value) -> Option<String> {
    record
        .get("current_version")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

fn document_urls(env: &Environment) -> Vec<(&str, String)> {
    DOCUMENTS
        .iter()
        .map(|(title, slug)| (*title, format!("{}/legal/{}", env.api_base, slug)))
        .collect()
}

/// `POST /api/me/tos-acceptance`. Idempotent for the current version.
pub async fn record_acceptance(api: &mut ApiClient, version: &str) -> Result<Value> {
    let response = api
        .post_json(ACCEPTANCE_PATH, Some(&serde_json::json!({ "version": version })))
        .await?;
    if response.status == 409 {
        return Err(freepod(format!(
            "the platform refused version '{version}': the terms changed between \
             reading them and accepting them. Re-run and review the current terms."
        )));
    }
    response.decode()
}

/// Show what is being agreed to, with somewhere to read it.
fn present(env: &Environment, echo: &dyn Fn(&str)) {
    echo("");
    echo("Before your first deployment, Freepod needs you to accept its terms.");
    let width = DOCUMENTS.iter().map(|(t, _)| t.chars().count()).max().unwrap_or(0);
    for (title, url) in document_urls(env) {
        let padded = format!("{title:<width$}");
        echo(&format!("  {padded}  {url}"));
    }
    echo("");
}

/// Offer the terms and record acceptance. Returns one of the outcome constants.
///
/// Never raises for a decline — refusing is a legitimate answer, and it is the
/// caller that knows whether the answer is fatal. It does raise for the read
/// and record network errors, which the caller surfaces.
pub async fn settle(
    api: &mut ApiClient,
    interactive: bool,
    echo: &dyn Fn(&str),
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<String> {
    let record = read(api).await?;
    if accepted(&record) {
        return Ok(ACCEPTED.to_string());
    }
    if !interactive {
        return Ok(NO_TERMINAL.to_string());
    }

    let Some(version) = current_version(&record) else {
        return Ok(VERSION_UNKNOWN.to_string());
    };

    present(&api.env, echo);
    if !ask(AGREEMENT)? {
        return Ok(DECLINED.to_string());
    }

    record_acceptance(api, &version).await?;
    echo(&format!("Accepted version {version}. This is recorded once, not per deployment."));
    Ok(ACCEPTED.to_string())
}

/// Why the deploy cannot proceed, and what would fix it.
pub fn explain(status: &str, env: &Environment) -> String {
    match status {
        VERSION_UNKNOWN => format!(
            "this platform does not report which version of its terms is current, \
             so they cannot be accepted from the command line.\n  Accept them at \
             {} and re-run. Nothing has been built or deployed.",
            env.api_base
        ),
        NO_TERMINAL => format!(
            "this account has not accepted the Freepod terms, and there is no \
             terminal to ask on.\n  Run `freepod login --env {}` from a terminal, or \
             accept them at {}, then re-run.",
            env.name, env.api_base
        ),
        _ => "the terms were not accepted, so no deployment can be created. Nothing has been built or deployed.".to_string(),
    }
}

/// Settle the terms, or refuse the deploy before anything is spent.
pub async fn require(
    api: &mut ApiClient,
    interactive: bool,
    echo: &dyn Fn(&str),
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<()> {
    let status = settle(api, interactive, echo, ask).await?;
    if status == ACCEPTED {
        return Ok(());
    }
    Err(freepod(explain(&status, &api.env)))
}
