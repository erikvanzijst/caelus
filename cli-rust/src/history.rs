//! The build history: reading an account's builds and rendering them.
//!
//! Mirrors `history.py`. A build is owned by a **user**, never by a deployment
//! or a project — the platform has no notion of a project at all. So this
//! lists the account's builds and annotates the one whose image the current
//! project is actually running.
//!
//! The table is the command's **result** and goes to stdout; the legend and
//! the counts are diagnostics and go to stderr.

use std::path::Path;

use chrono::{DateTime, Utc};
use serde_json::Value;

use crate::api::ApiClient;
use crate::errors::{freepod, Result};
use crate::project::{find_project_root, load};
use crate::table::{abbreviate, elapsed, format_duration, format_time, value_str, BLANK};

/// How many builds a bare `freepod builds` shows.
pub const DEFAULT_LIMIT: usize = 20;

/// Marks the build whose image the project's deployment is currently running.
pub const LIVE_MARKER: &str = "*";

const COLUMNS: [&str; 6] = ["", "BUILD", "STATUS", "CREATED", "DURATION", "IMAGE"];

/// `GET /api/users/{user_id}/builds` — the account's builds, most recent first.
pub async fn list_builds(api: &mut ApiClient, user_id: u64) -> Result<Vec<Value>> {
    let path = format!("/api/users/{user_id}/builds");
    let body = api.get_json(&path, None).await?;
    let arr = body
        .as_array()
        .ok_or_else(|| freepod(format!("unexpected {path} response: {body}")))?;
    Ok(arr.iter().filter(|e| e.is_object()).cloned().collect())
}

/// The image this project's deployment runs, if there is one to read.
pub async fn deployed_image(
    api: &mut ApiClient,
    user_id: u64,
    env_name: &str,
    root: Option<&Path>,
) -> Option<String> {
    let found = find_project_root(root)?;
    let project = load(&found).ok()?;
    let deployment_id = project.deployment_id()?;
    if project.env != env_name {
        return None;
    }
    let response = api
        .get(
            &format!("/api/users/{user_id}/deployments/{deployment_id}"),
            None,
        )
        .await
        .ok()?;
    if !response.is_success() {
        return None;
    }
    let body = response.decode().ok()?;
    let image = body
        .get("user_values_json")?
        .get("image")
        .and_then(|v| v.as_str())?;
    if image.is_empty() {
        return None;
    }
    Some(image.to_string())
}

/// How long the build ran, or has been running.
fn duration(build: &Value, now: Option<DateTime<Utc>>) -> Option<chrono::Duration> {
    let null = Value::Null;
    let started = build.get("started_at").unwrap_or(&null);
    let finished = build.get("finished_at").unwrap_or(&null);
    elapsed(started, finished, now)
}

/// One row per build, in the order given, headers first.
pub fn rows(
    builds: &[Value],
    live_image: Option<&str>,
    full_image: bool,
    now: Option<DateTime<Utc>>,
) -> Vec<Vec<String>> {
    let mut table: Vec<Vec<String>> = vec![COLUMNS.iter().map(|s| s.to_string()).collect()];
    for build in builds {
        let null = Value::Null;
        let image = build.get("image").unwrap_or(&null);
        let live = live_image
            .map(|li| image.as_str() == Some(li))
            .unwrap_or(false);
        table.push(vec![
            if live {
                LIVE_MARKER.to_string()
            } else {
                String::new()
            },
            build
                .get("id")
                .map(value_str)
                .unwrap_or_else(|| BLANK.to_string()),
            build
                .get("status")
                .map(value_str)
                .unwrap_or_else(|| BLANK.to_string()),
            format_time(build.get("created_at").unwrap_or(&null)),
            format_duration(duration(build, now)),
            abbreviate(image, full_image),
        ]);
    }
    table
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn rows_marks_the_live_build() {
        let builds = vec![
            json!({ "id": "b1", "status": "succeeded", "image": "reg/app@sha256:deadbeefdeadbeef" }),
            json!({ "id": "b2", "status": "succeeded", "image": "reg/app@sha256:cafebabe" }),
        ];
        let table = rows(&builds, Some("reg/app@sha256:cafebabe"), false, None);
        assert_eq!(table.len(), 3);
        assert_eq!(table[0][0], "");
        assert_eq!(table[1][0], "");
        assert_eq!(table[2][0], LIVE_MARKER);
        assert_eq!(table[2][1], "b2");
    }

    #[test]
    fn rows_abbreviates_by_default() {
        let builds = vec![json!({
            "id": "b1",
            "status": "succeeded",
            "image": "reg/app@sha256:0123456789abcdef0123456789abcdef"
        })];
        let table = rows(&builds, None, false, None);
        assert!(table[1][5].ends_with('…'), "{}", table[1][5]);
        let full = rows(&builds, None, true, None);
        assert_eq!(full[1][5], "reg/app@sha256:0123456789abcdef0123456789abcdef");
    }
}
