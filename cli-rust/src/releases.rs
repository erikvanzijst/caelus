//! The release history: what this project's deployment has rolled out.
//!
//! Mirrors `releases.py`. Unlike the build history, this one is inherently
//! project-scoped — a release belongs to a deployment. The running release is
//! marked from what the deployment reports as *applied*, never from the top of
//! the listing: after a failed rollout the newest release is not the one
//! serving traffic.

use chrono::{DateTime, Utc};
use serde_json::Value;

use crate::api::ApiClient;
use crate::errors::{freepod, Result};
use crate::table::{abbreviate, elapsed, format_duration, format_time, render, value_str, BLANK};

/// How many releases a bare `freepod releases` shows.
pub const DEFAULT_LIMIT: usize = 20;

/// Marks the release the deployment is currently running.
pub const LIVE_MARKER: &str = "*";

const COLUMNS: [&str; 6] = ["", "RELEASE", "STATUS", "CREATED", "DURATION", "IMAGE"];

/// The deployment's releases, most recent first.
pub async fn list_releases(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
) -> Result<Vec<Value>> {
    let path = format!("/api/users/{user_id}/deployments/{deployment_id}/releases");
    let body = api.get_json(&path, None).await?;
    let arr = body
        .as_array()
        .ok_or_else(|| freepod(format!("unexpected {path} response: {body}")))?;
    Ok(arr.iter().filter(|e| e.is_object()).cloned().collect())
}

/// The deployment, or None where the platform no longer has it.
pub async fn read_deployment(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
) -> Option<Value> {
    let response = api
        .get(&format!("/api/users/{user_id}/deployments/{deployment_id}"), None)
        .await
        .ok()?;
    if !response.is_success() {
        return None;
    }
    response.decode().ok().filter(|v| v.is_object())
}

/// The number of the release the deployment is running, if it reports one.
pub fn applied_number(deployment: Option<&Value>) -> Option<u64> {
    let applied = deployment?.get("applied_release")?;
    applied.get("number").and_then(|v| v.as_u64())
}

/// The image the release shipped, from the build inlined on it.
pub fn image_of(release: &Value) -> Option<String> {
    let image = release.get("build")?.get("image")?.as_str()?;
    if image.is_empty() {
        return None;
    }
    Some(image.to_string())
}

/// `(number, error)` lines for the releases that recorded one.
pub fn failures(releases: &[Value]) -> Vec<String> {
    let mut notes = Vec::new();
    for release in releases {
        let Some(error) = release.get("error").and_then(|v| v.as_str()) else {
            continue;
        };
        if error.trim().is_empty() {
            continue;
        }
        let number = release
            .get("number")
            .map(value_str)
            .unwrap_or_else(|| BLANK.to_string());
        notes.push(format!("release {number} failed: {}", error.trim()));
    }
    notes
}

/// One row per release, in the order given, headers first.
pub fn rows(
    releases: &[Value],
    live_number: Option<u64>,
    full_image: bool,
    now: Option<DateTime<Utc>>,
) -> Vec<Vec<String>> {
    let mut table: Vec<Vec<String>> = vec![COLUMNS.iter().map(|s| s.to_string()).collect()];
    for release in releases {
        let null = Value::Null;
        let number = release.get("number").and_then(|v| v.as_u64());
        let live = live_number.map(|ln| number == Some(ln)).unwrap_or(false);
        let image = image_of(release).map(Value::String).unwrap_or(Value::Null);
        let started = release.get("started_at").unwrap_or(&null);
        let ended = release.get("ended_at").unwrap_or(&null);
        table.push(vec![
            if live {
                LIVE_MARKER.to_string()
            } else {
                String::new()
            },
            number
                .map(|n| n.to_string())
                .unwrap_or_else(|| BLANK.to_string()),
            release
                .get("status")
                .map(value_str)
                .unwrap_or_else(|| BLANK.to_string()),
            format_time(release.get("created_at").unwrap_or(&null)),
            format_duration(elapsed(started, ended, now)),
            abbreviate(&image, full_image),
        ]);
    }
    table
}

/// The rendered table, ready for stdout.
pub fn render_table(
    releases: &[Value],
    live_number: Option<u64>,
    full_image: bool,
    now: Option<DateTime<Utc>>,
) -> String {
    render(&rows(releases, live_number, full_image, now))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn applied_number_reads_the_applied_release() {
        let d = json!({ "applied_release": { "number": 7 } });
        assert_eq!(applied_number(Some(&d)), Some(7));
        assert_eq!(applied_number(None), None);
        assert_eq!(applied_number(Some(&json!({}))), None);
    }

    #[test]
    fn image_of_reads_the_inlined_build() {
        let r = json!({ "build": { "image": "reg/app@sha256:abc" } });
        assert_eq!(image_of(&r).as_deref(), Some("reg/app@sha256:abc"));
        assert_eq!(image_of(&json!({})), None);
    }

    #[test]
    fn failures_collect_only_the_recorded_ones() {
        let releases = vec![
            json!({ "number": 1, "error": "boom" }),
            json!({ "number": 2, "error": "   " }),
            json!({ "number": 3 }),
        ];
        let notes = failures(&releases);
        assert_eq!(notes, vec!["release 1 failed: boom"]);
    }

    #[test]
    fn rows_mark_the_live_release() {
        let releases = vec![json!({ "number": 5, "status": "ready" })];
        let table = rows(&releases, Some(5), false, None);
        assert_eq!(table[1][0], LIVE_MARKER);
        assert_eq!(table[1][1], "5");
    }
}
