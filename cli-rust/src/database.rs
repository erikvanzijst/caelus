//! `freepod db`: the deployment's PostgreSQL database.
//!
//! Mirrors `database.py`.
//!
//! **No address, and no connection URL.** The platform reports the pooler's
//! host and port, and both resolve inside the cluster and nowhere else — so a
//! URL built around them would look exactly like the input to `psql` and
//! connect from nowhere the reader is standing. The URL that will connect is
//! the one the forwarding client composes around its own local address, which
//! is also why it cannot use a server-composed one. What this module reports
//! is the part that stays true on both sides of that tunnel: which database
//! and role the deployment owns, the password that owns them, and how much of
//! the allowance is used.

use serde_json::Value;

use crate::api::ApiClient;
use crate::errors::{freepod, Result};
use crate::table::{format_time, render, value_str};

pub const NO_DATABASE_CODE: &str = "relational_storage_unavailable";

/// Fixed width, so the mask does not report the password's length.
pub const MASK: &str = "••••••••••••";

pub const REVEAL_HINT: &str = "(--show-password to reveal)";

/// What each quota state means to the person who owns the data. A state name
/// on its own answers nothing: someone runs this command *because* writes
/// started failing.
fn state_consequence(state: Option<&str>) -> String {
    match state {
        Some("ok") => "healthy".to_string(),
        Some("warned") => "approaching its allowance".to_string(),
        Some("readonly") => {
            "read-only — over its allowance, so every write is rejected".to_string()
        }
        Some("blocked") => {
            "suspended — far over its allowance, so your app cannot connect".to_string()
        }
        other => other.map(String::from).unwrap_or_default(),
    }
}

/// The deployment's database details, or None when it has none.
///
/// None is an answer rather than a failure: a product that offers no
/// relational storage is a normal state, and so is the interval before a new
/// deployment's first reconcile has provisioned one. Both carry the platform's
/// stable code; a 404 without it is a missing deployment and stays an error.
pub async fn read(api: &mut ApiClient, user_id: u64, deployment_id: &str) -> Result<Option<Value>> {
    let path = format!("/api/users/{user_id}/deployments/{deployment_id}/database");
    let response = api.get(&path, None).await?;
    if response.status == 404 {
        let body: Value = serde_json::from_slice(&response.body).unwrap_or(Value::Null);
        if body.get("code").and_then(|v| v.as_str()) == Some(NO_DATABASE_CODE) {
            return Ok(None);
        }
        let detail = body
            .get("detail")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        return Err(freepod(if detail.is_empty() {
            "no such deployment".to_string()
        } else {
            detail
        }));
    }

    if !response.is_success() {
        return Err(freepod(format!(
            "HTTP {} from {}: {}",
            response.status,
            response.url,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    let body = response.decode()?;
    if !body.is_object() {
        return Err(freepod(format!("unexpected database response: {body}")));
    }
    Ok(Some(body))
}

pub fn format_bytes(count: u64) -> String {
    const KB: u64 = 1024;
    const MB: u64 = 1024 * 1024;
    const GB: u64 = 1024 * 1024 * 1024;
    const TB: u64 = 1024 * 1024 * 1024 * 1024;
    if count >= TB {
        format!("{:.1} TB", count as f64 / TB as f64)
    } else if count >= GB {
        format!("{:.1} GB", count as f64 / GB as f64)
    } else if count >= MB {
        format!("{:.0} MB", count as f64 / MB as f64)
    } else if count >= KB {
        format!("{:.0} KB", count as f64 / KB as f64)
    } else {
        format!("{count} B")
    }
}

/// How full the database is, as a percentage with the figures behind it.
pub fn format_usage(size: u64, allowance: u64) -> String {
    let figures = format!("{} of {}", format_bytes(size), format_bytes(allowance));
    if allowance == 0 {
        return figures;
    }
    let percent = size as f64 / allowance as f64 * 100.0;
    let shown = if percent > 0.0 && percent < 1.0 {
        "<1".to_string()
    } else {
        percent.round().to_string()
    };
    format!("{shown}% ({figures})")
}

/// Usage against the allowance, with the age of the figure.
///
/// A never-measured database (`size_bytes` null) is not a zero measurement.
fn usage_text(details: &Value) -> String {
    let allowance = details.get("allowance_bytes").and_then(|v| v.as_u64());
    let allowance_text = allowance
        .map(format_bytes)
        .unwrap_or_else(|| "unknown".to_string());
    match details.get("size_bytes").and_then(|v| v.as_u64()) {
        None => format!("not yet measured (allowance {allowance_text})"),
        Some(size) => match allowance {
            None => format!("{} (allowance {allowance_text})", format_bytes(size)),
            Some(allowance) => format!(
                "{} — measured {}",
                format_usage(size, allowance),
                format_time(details.get("measured_at").unwrap_or(&Value::Null))
            ),
        },
    }
}

/// The command's result: identity, credential and health, as a table.
///
/// The response carries the pooler's `host` and `port`; neither is rendered.
pub fn render_status(details: &Value, show_password: bool) -> String {
    let shown = match details.get("password") {
        None | Some(Value::Null) => "withheld — only the owner can read it".to_string(),
        Some(v) if show_password => value_str(v),
        Some(_) => format!("{MASK} {REVEAL_HINT}"),
    };

    let rows = vec![
        vec![
            "Database".to_string(),
            details.get("database").map(value_str).unwrap_or_default(),
        ],
        vec![
            "Role".to_string(),
            details.get("role").map(value_str).unwrap_or_default(),
        ],
        vec!["Password".to_string(), shown],
        vec!["Usage".to_string(), usage_text(details)],
        vec![
            "State".to_string(),
            state_consequence(details.get("quota_state").and_then(|v| v.as_str())),
        ],
    ];
    render(&rows)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const MEGABYTE: u64 = 1024 * 1024;

    const PASSWORD: &str = "p@ss/w:rd?#[]&=+ 90%";
    const POOLER_HOST: &str = "caelus-tenant-pooler.caelus-tenant.svc.cluster.local";

    fn details(overrides: serde_json::Map<String, Value>) -> Value {
        let mut body = json!({
            "host": POOLER_HOST,
            "port": 6432,
            "database": "dpl_0f2c",
            "role": "dpl_0f2c",
            "password": PASSWORD,
            "password_withheld": false,
            "quota_state": "ok",
            "allowance_bytes": 100 * MEGABYTE,
            "size_bytes": 42 * MEGABYTE,
            "measured_at": "2026-08-29T09:14:00"
        });
        for (k, v) in overrides {
            body[k] = v;
        }
        body
    }

    // --- format_bytes --------------------------------------------------------

    #[test]
    fn format_bytes_scales() {
        assert_eq!(format_bytes(0), "0 B");
        assert_eq!(format_bytes(1023), "1023 B");
        assert_eq!(format_bytes(2048), "2 KB");
        assert_eq!(format_bytes(42 * MEGABYTE), "42 MB");
        assert_eq!(format_bytes(3 * 1024 * 1024 * 1024), "3.0 GB");
        assert_eq!(format_bytes(2 * 1024 * 1024 * 1024 * 1024), "2.0 TB");
    }

    // --- format_usage ----------------------------------------------------------

    #[test]
    fn format_usage_matches_the_dashboard() {
        assert_eq!(
            format_usage(42 * MEGABYTE, 100 * MEGABYTE),
            "42% (42 MB of 100 MB)"
        );
        assert_eq!(format_usage(0, 100 * MEGABYTE), "0% (0 B of 100 MB)");
        assert_eq!(
            format_usage(64 * 1024, 100 * MEGABYTE),
            "<1% (64 KB of 100 MB)"
        );
        assert_eq!(
            format_usage(142 * MEGABYTE, 100 * MEGABYTE),
            "142% (142 MB of 100 MB)"
        );
    }

    #[test]
    fn format_usage_zero_allowance_shows_figures_only() {
        assert_eq!(format_usage(42 * MEGABYTE, 0), "42 MB of 0 B");
    }

    // --- usage_text -------------------------------------------------------------

    #[test]
    fn never_measured_is_not_reported_as_zero() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("size_bytes".into(), Value::Null);
        overrides.insert("measured_at".into(), Value::Null);
        let text = usage_text(&details(overrides));
        assert_eq!(text, "not yet measured (allowance 100 MB)");
        assert!(!text.contains("0 B"));
    }

    #[test]
    fn measured_at_zero_is_a_measurement() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("size_bytes".into(), json!(0));
        let text = usage_text(&details(overrides));
        assert!(text.starts_with("0% (0 B of 100 MB)"));
        assert!(text.contains("measured"));
    }

    #[test]
    fn a_missing_allowance_is_said_not_guessed() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("allowance_bytes".into(), Value::Null);
        let text = usage_text(&details(overrides));
        assert_eq!(text, "42 MB (allowance unknown)");
    }

    #[test]
    fn a_size_carries_the_age_of_its_measurement() {
        let text = usage_text(&details(serde_json::Map::new()));
        assert!(text.contains("measured"));
    }

    // --- render_status -----------------------------------------------------------

    #[test]
    fn the_password_is_masked_with_a_fixed_width_mask() {
        let out = render_status(&details(serde_json::Map::new()), false);
        assert!(!out.contains(PASSWORD));
        assert!(out.contains(REVEAL_HINT));
        assert!(out.contains(MASK));
        assert_eq!(MASK.chars().count(), 12);
        // The mask must not report the password's length: a one-character
        // password masks to the same cell as a long one.
        let mut overrides = serde_json::Map::new();
        overrides.insert("password".into(), json!("x"));
        let short = render_status(&details(overrides), false);
        let mask_line = |out: &str| {
            out.lines()
                .find(|l| l.starts_with("Password"))
                .unwrap()
                .to_string()
        };
        assert_eq!(mask_line(&out), mask_line(&short));
    }

    #[test]
    fn show_password_prints_it() {
        let out = render_status(&details(serde_json::Map::new()), true);
        assert!(out.contains(PASSWORD));
        assert!(!out.contains(MASK));
    }

    #[test]
    fn a_withheld_password_is_stated_rather_than_shown_as_absent() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("password".into(), Value::Null);
        overrides.insert("password_withheld".into(), json!(true));
        let out = render_status(&details(overrides), false);
        assert!(out.to_lowercase().contains("withheld"));
        assert!(!out.contains("--show-password"));
    }

    #[test]
    fn readonly_says_writes_are_rejected() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("quota_state".into(), json!("readonly"));
        let out = render_status(&details(overrides), false);
        assert!(out.contains("read-only"));
        assert!(out.contains("rejected"));
    }

    #[test]
    fn blocked_says_the_app_cannot_connect() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("quota_state".into(), json!("blocked"));
        let out = render_status(&details(overrides), false);
        assert!(out.contains("suspended"));
        assert!(out.contains("cannot connect"));
    }

    #[test]
    fn ok_says_healthy() {
        let out = render_status(&details(serde_json::Map::new()), false);
        assert!(out.contains("healthy"));
        assert!(out.contains("dpl_0f2c"));
        assert!(out.contains("42% (42 MB of 100 MB)"));
    }

    #[test]
    fn an_unknown_state_is_shown_raw() {
        let mut overrides = serde_json::Map::new();
        overrides.insert("quota_state".into(), json!("curious"));
        let out = render_status(&details(overrides), false);
        assert!(out.contains("curious"));
    }

    #[test]
    fn no_flag_combination_prints_an_address() {
        for show_password in [false, true] {
            let out = render_status(&details(serde_json::Map::new()), show_password);
            assert!(!out.contains(POOLER_HOST), "host leaked");
            assert!(!out.contains("6432"), "port leaked");
            assert!(!out.contains("postgresql://"), "URL leaked");
        }
    }
}
