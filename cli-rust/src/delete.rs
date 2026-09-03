//! Deleting the deployment a project points at.
//!
//! Mirrors `delete.py`. The mirror image of `deploy`, and deliberately the only
//! destructive thing this client does. It addresses the deployment recorded in
//! the project file and nothing else.
//!
//! Teardown is asynchronous: `DELETE` answers **204** and moves the deployment
//! to `deleting`; the reconciler uninstalls the release afterwards. The client
//! follows the teardown to `deleted` by default, because the hostname stays
//! claimed until it lands.

use std::path::Path;
use std::time::{Duration, Instant};

use serde_json::Value;

use crate::api::ApiClient;
use crate::deploy::describe_conflict;
use crate::errors::{freepod, usage, Result};
use crate::project::{require_project, Project, PROJECT_FILE};

/// Where a teardown ends.
pub const STATUS_DELETED: &str = "deleted";
/// In flight.
const STATUS_DELETING: &str = "deleting";
const STATUS_ERROR: &str = "error";

/// How often to re-read while following a teardown.
pub const POLL_SECONDS: f64 = 3.0;

/// The deployment, or None if the platform no longer has it.
async fn read_deployment(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
) -> Result<Option<Value>> {
    let response = api
        .get(&format!("/api/users/{user_id}/deployments/{deployment_id}"), None)
        .await?;
    if response.status == 404 {
        return Ok(None);
    }
    if !response.is_success() {
        return Err(freepod(format!(
            "could not read deployment {deployment_id}: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    Ok(Some(response.decode()?))
}

/// `https://…` for a deployment's hostname, or None.
fn address(deployment: &Value) -> Option<String> {
    deployment
        .get("hostname")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|h| format!("https://{h}"))
}

/// Show what is about to be destroyed, by name and by address.
fn present(deployment: &Value, env_name: &str, echo: &dyn Fn(&str)) {
    echo("");
    echo(&format!(
        "About to delete deployment '{}' on '{env_name}':",
        deployment.get("name").and_then(|v| v.as_str()).unwrap_or("?")
    ));
    if let Some(live) = address(deployment) {
        echo(&format!("  address  {live}"));
    }
    echo(&format!(
        "  status   {}",
        deployment.get("status").and_then(|v| v.as_str()).unwrap_or("?")
    ));
    echo(&format!(
        "  id       {}",
        deployment.get("id").and_then(|v| v.as_str()).unwrap_or("?")
    ));
    echo("");
    echo(
        "This tears down the deployment and destroys everything it stores. It \
         cannot be undone.",
    );
}

/// Whether to go ahead. `--yes` answers in advance; nothing else may.
fn confirm(
    deployment: &Value,
    env_name: &str,
    assume_yes: bool,
    interactive: bool,
    echo: &dyn Fn(&str),
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<bool> {
    if assume_yes {
        return Ok(true);
    }
    if !interactive {
        return Err(usage(
            "deleting a deployment needs confirmation and there is no terminal to \
             ask on.\n  Re-run with --yes to confirm in advance. Nothing has been \
             deleted.",
        ));
    }
    present(deployment, env_name, echo);
    ask(&format!(
        "Delete '{}'?",
        deployment.get("name").and_then(|v| v.as_str()).unwrap_or("?")
    ))
}

/// `DELETE /api/users/{user_id}/deployments/{deployment_id}`.
async fn request_deletion(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
) -> Result<()> {
    let response = api
        .delete(&format!("/api/users/{user_id}/deployments/{deployment_id}"))
        .await?;
    if response.status == 404 {
        return Ok(());
    }
    if response.status == 409 {
        let (message, retryable) = describe_conflict(response.detail().as_deref(), None);
        let message = if retryable {
            format!("{message}\n  Nothing has been deleted.")
        } else {
            message
        };
        return Err(freepod(message));
    }
    if !(response.status == 200 || response.status == 202 || response.status == 204) {
        return Err(freepod(format!(
            "could not delete deployment {deployment_id}: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    Ok(())
}

/// Poll until the deployment is `deleted`, or the platform says it failed.
async fn wait_until_gone(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    timeout: u64,
    poll: f64,
    echo: &dyn Fn(&str),
) -> Result<()> {
    let mut reported: Option<String> = None;
    let deadline = Instant::now() + Duration::from_secs(timeout);

    loop {
        let Some(record) = read_deployment(api, user_id, deployment_id).await? else {
            return Ok(());
        };
        let status = record
            .get("status")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        if status == STATUS_DELETED {
            return Ok(());
        }
        if status == STATUS_ERROR {
            let last_error = record
                .get("last_error")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .unwrap_or("no error message");
            return Err(freepod(format!(
                "the teardown of deployment {deployment_id} failed on the platform.\n  \
                 The platform recorded: {last_error}\n  The deployment may still hold \
                 its hostname. Delete it from {} once the cause is resolved.",
                api.env.api_base
            )));
        }

        if reported.as_deref() != Some(status.as_str()) {
            echo(&format!("  {status}..."));
            reported = Some(status.clone());
        }

        if Instant::now() >= deadline {
            return Err(freepod(format!(
                "stopped waiting after {timeout}s. Deployment {deployment_id} is still \
                 being torn down on the platform — the deletion was not canceled, and \
                 {PROJECT_FILE} no longer points at it."
            )));
        }
        tokio::time::sleep(Duration::from_secs_f64(poll)).await;
    }
}

/// Delete this project's deployment. Returns whether anything was deleted.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
pub async fn delete(
    api: &mut ApiClient,
    env_name: &str,
    root: Option<&Path>,
    assume_yes: bool,
    wait: bool,
    interactive: bool,
    timeout: u64,
    poll: f64,
    echo: &dyn Fn(&str),
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<bool> {
    let mut project = require_project(root)?;

    if project.env != env_name && project.deployment_id().is_some() {
        return Err(usage(format!(
            "{} records deployment '{}' on '{}', not on '{env_name}'.\n  Re-run without \
             --env (or with --env {}) to delete it.",
            project.path().display(),
            project.deployment_name().unwrap_or(""),
            project.env,
            project.env
        )));
    }

    let Some(deployment_id) = project.deployment_id().map(|s| s.to_string()) else {
        return Err(usage(format!(
            "{} records no deployment, so there is nothing to delete.\n  Run `freepod \
             deploy` to create one.",
            project.path().display()
        )));
    };

    // `/api/me` first, as everywhere.
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let record = read_deployment(api, user_id, &deployment_id).await?;

    let Some(record) = record else {
        // Gone already — clearing the stale pointer is the whole of what is left.
        let name = project.deployment_name().map(|n| format!(" ({n})")).unwrap_or_default();
        echo(&format!(
            "Deployment {deployment_id}{name} no longer exists on '{env_name}'; nothing \
             to delete."
        ));
        forget(&mut project, echo)?;
        return Ok(false);
    };

    let status = record
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if status == STATUS_DELETING || status == STATUS_DELETED {
        echo(&format!(
            "Deployment '{}' is already {status}.",
            record.get("name").and_then(|v| v.as_str()).unwrap_or("?")
        ));
        forget(&mut project, echo)?;
        if wait && status == STATUS_DELETING {
            wait_until_gone(api, user_id, &deployment_id, timeout, poll, echo).await?;
            echo("Deleted.");
        }
        return Ok(false);
    }

    if !confirm(&record, env_name, assume_yes, interactive, echo, ask)? {
        echo("Nothing was deleted.");
        return Ok(false);
    }

    request_deletion(api, user_id, &deployment_id).await?;
    echo(&format!(
        "Deleting deployment '{}' ({deployment_id})...",
        record.get("name").and_then(|v| v.as_str()).unwrap_or("?")
    ));

    // Discarded now, not after the wait.
    forget(&mut project, echo)?;

    if wait {
        wait_until_gone(api, user_id, &deployment_id, timeout, poll, echo).await?;
        echo("Deleted.");
    } else {
        echo(
            "Teardown continues on the platform. Its hostname stays claimed until it \
             finishes.",
        );
    }
    Ok(true)
}

fn forget(project: &mut Project, echo: &dyn Fn(&str)) -> Result<()> {
    project.forget_deployment()?;
    echo(&format!("Cleared the deployment pointer in {}.", project.path().display()));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn address_uses_https() {
        let d = json!({ "hostname": "foo.freepod.eu" });
        assert_eq!(address(&d).as_deref(), Some("https://foo.freepod.eu"));
        assert_eq!(address(&json!({})), None);
    }
}
