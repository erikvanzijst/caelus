//! The build pipeline: upload the packed archive to a presigned object-store
//! slot, open a build against it, and follow the build log to a terminal
//! status. Mirrors `build.py`.
//!
//! The upload is a multipart POST to a presigned URL minted by the platform:
//! the file part is the only one the platform cannot sign for, so it goes
//! last; the signed `fields` are sent verbatim, in the order minted. The
//! object store is a different host with a different credential model, so it
//! is reached with a plain client, not the API client.

use std::io::{IsTerminal, Write};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::api::ApiClient;
use crate::archive::human;
use crate::config::USER_AGENT;
use crate::errors::{build_failed, freepod, Result};

/// The build states that end the wait. Everything else keeps polling.
pub const TERMINAL_STATUSES: &[&str] = &["succeeded", "failed", "canceled"];

pub const STATUS_QUEUED: &str = "queued";
pub const STATUS_SUCCEEDED: &str = "succeeded";

/// The poll interval while the log is actively growing.
const POLL_ACTIVE_SECONDS: f64 = 1.0;
/// The poll interval while the log is quiet.
const POLL_IDLE_SECONDS: f64 = 3.0;
/// The object store is a different host; the upload gets its own, generous
/// ceiling rather than the API's per-request timeout.
const UPLOAD_TIMEOUT_SECONDS: u64 = 900;

/// A finished, successful build: the image reference and the build's identity.
pub struct Built {
    pub image: String,
    pub build_id: String,
}

/// Mint a fresh upload slot: `POST /api/artifacts`.
pub async fn mint_slot(api: &mut ApiClient) -> Result<Value> {
    let response = api.post_json("/api/artifacts", None).await?;
    if response.status != 201 {
        return Err(freepod(format!(
            "could not obtain an upload slot: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    let slot = response.decode()?;
    for key in ["artifact_id", "url", "fields", "max_bytes"] {
        if slot.get(key).is_none() {
            return Err(freepod(format!("upload slot is missing '{key}': {slot}")));
        }
    }
    Ok(slot)
}

/// Refuse archives the platform will not accept, before spending a slot.
pub fn check_size(size: usize, slot: &Value) -> Result<()> {
    let limit = slot
        .get("max_bytes")
        .and_then(|v| v.as_u64())
        .unwrap_or(0) as usize;
    if size > limit {
        return Err(freepod(format!(
            "the packed archive is {} ({} bytes), which exceeds this platform's limit of \
             {} ({} bytes).\n  Exclude what the build does not need — a .freepodignore \
             works like .gitignore — and try again.",
            human(size as u64),
            size,
            human(limit as u64),
            limit
        )));
    }
    Ok(())
}

/// POST the archive to the presigned URL: the minted fields first, the file
/// last. Returns the store's status and body for the caller to interpret.
async fn submit(
    store: &reqwest::Client,
    slot: &Value,
    archive: &[u8],
    quiet: bool,
) -> Result<(u16, String)> {
    let url = slot
        .get("url")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    let mut form = reqwest::multipart::Form::new();
    if let Some(fields) = slot.get("fields").and_then(|v| v.as_object()) {
        for (key, value) in fields {
            let text = value.as_str().unwrap_or_default().to_string();
            form = form.text(key.clone(), text);
        }
    }
    let part = reqwest::multipart::Part::bytes(archive.to_vec())
        .file_name("archive.tar.gz")
        .mime_str("application/gzip")
        .map_err(|e| freepod(format!("cannot build the upload form: {e}")))?;
    form = form.part("file", part);

    if !quiet && std::io::stderr().is_terminal() {
        eprintln!("  uploading {}", human(archive.len() as u64));
    }

    let response = store
        .post(&url)
        .multipart(form)
        .header("User-Agent", USER_AGENT)
        .timeout(Duration::from_secs(UPLOAD_TIMEOUT_SECONDS))
        .send()
        .await
        .map_err(|e| freepod(format!("cannot reach {url}: {e}")))?;
    let status = response.status().as_u16();
    let body = response.text().await.unwrap_or_default();
    Ok((status, body))
}

/// Upload the packed archive and return the platform's artifact id for it.
///
/// A 403 from the store is retried once with a fresh slot: a slot can be
/// rejected if it was minted long before the upload. Any other refusal is
/// final.
pub async fn upload_archive(
    api: &mut ApiClient,
    archive: &[u8],
    size: usize,
    store: &reqwest::Client,
    quiet: bool,
    echo: &dyn Fn(&str),
) -> Result<String> {
    let mut slot = mint_slot(api).await?;
    check_size(size, &slot)?;
    let (mut status, mut body) = submit(store, &slot, archive, quiet).await?;
    if status == 403 {
        echo("  upload slot rejected; obtaining a fresh one and retrying once.");
        slot = mint_slot(api).await?;
        check_size(size, &slot)?;
        (status, body) = submit(store, &slot, archive, quiet).await?;
    }
    if !(status == 200 || status == 201 || status == 204) {
        return Err(freepod(format!(
            "the object store refused the upload: HTTP {status} {}",
            body.trim().chars().take(500).collect::<String>()
        )));
    }
    let artifact_id = slot
        .get("artifact_id")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    Ok(artifact_id)
}

/// Open a build against the artifact: `POST /api/users/{id}/builds`.
///
/// Returns the build record and whether it was re-attached (200) rather than
/// newly created (201): the platform reuses an in-flight build for the same
/// artifact, so a retry resumes it instead of starting a second.
pub async fn create_build(
    api: &mut ApiClient,
    user_id: u64,
    artifact_id: &str,
) -> Result<(Value, bool)> {
    let path = format!("/api/users/{}/builds", user_id);
    let response = api
        .post_json(&path, Some(&json!({ "artifact_id": artifact_id })))
        .await?;
    if response.status != 200 && response.status != 201 {
        return Err(freepod(format!(
            "could not create the build: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    let build = response.decode()?;
    Ok((build, response.status == 200))
}

/// Follow the build log to a terminal status, streaming it to `out`.
///
/// The log is resumable: each poll asks for the bytes from where the last one
/// stopped, so a slow build is a series of small reads rather than one long
/// connection. The platform's current state rides in the `X-Build-Status`
/// header; the wait ends when it is terminal or the deadline passes.
pub async fn follow_build(
    api: &mut ApiClient,
    user_id: u64,
    build_id: &str,
    out: &mut (impl Write + Unpin),
    timeout: u64,
    echo: &dyn Fn(&str),
) -> Result<String> {
    let mut offset: u64 = 0;
    let mut status = STATUS_QUEUED.to_string();
    let mut announced_queued = false;
    let deadline = Instant::now() + Duration::from_secs(timeout);
    loop {
        let path = format!("/api/users/{}/builds/{}/log", user_id, build_id);
        let headers = [("Range".to_string(), format!("bytes={offset}-"))];
        let response = api.request("GET", &path, None, None, Some(&headers)).await?;
        if response.status != 200 && response.status != 206 {
            return Err(freepod(format!(
                "could not read the build log: HTTP {} {}",
                response.status,
                response.text().trim().chars().take(300).collect::<String>()
            )));
        }
        if let Some(current) = response.header("X-Build-Status") {
            status = current;
        }
        let chunk = response.body.clone();
        if !chunk.is_empty() {
            out.write_all(&chunk)
                .map_err(|e| freepod(format!("cannot write the build log: {e}")))?;
            out.flush()
                .map_err(|e| freepod(format!("cannot write the build log: {e}")))?;
            offset += chunk.len() as u64;
        }
        if TERMINAL_STATUSES.contains(&status.as_str()) {
            return Ok(status);
        }
        if status == STATUS_QUEUED && !announced_queued {
            echo("  Queued — waiting for a build worker...");
            announced_queued = true;
        }
        if Instant::now() >= deadline {
            return Err(freepod(format!(
                "stopped waiting after {}s. The build is still running on the platform — \
                 it was not canceled (build {build_id}).",
                timeout
            )));
        }
        let poll = if chunk.is_empty() {
            POLL_IDLE_SECONDS
        } else {
            POLL_ACTIVE_SECONDS
        };
        tokio::time::sleep(Duration::from_secs_f64(poll)).await;
    }
}

/// The whole pipeline: upload, build, and wait. Returns the image on success,
/// and raises a build failure (exit 4) on any other terminal status.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
pub async fn build_image(
    api: &mut ApiClient,
    user_id: u64,
    archive: &[u8],
    size: usize,
    store: &reqwest::Client,
    out: &mut (impl Write + Unpin),
    timeout: u64,
    quiet: bool,
    echo: &dyn Fn(&str),
) -> Result<Built> {
    let artifact_id = upload_archive(api, archive, size, store, quiet, echo).await?;
    let (build, reattached) = create_build(api, user_id, &artifact_id).await?;
    let build_id = build
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string();
    if reattached {
        echo(&format!(
            "  Re-attaching to the build already in progress for this archive ({build_id})."
        ));
    } else {
        echo(&format!("  Build {build_id} queued."));
    }
    let status = follow_build(api, user_id, &build_id, out, timeout, echo).await?;
    if status != STATUS_SUCCEEDED {
        return Err(build_failed(format!(
            "the build {status} (build {build_id}). Nothing has been deployed; the log above \
             is the platform's account of why."
        )));
    }
    let record = api
        .get_json(&format!("/api/users/{}/builds/{}", user_id, build_id), None)
        .await?;
    let Some(image) = record
        .get("image")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
    else {
        return Err(freepod(format!(
            "build {build_id} succeeded but carries no image reference — this is an \
             unexpected platform condition, please report it."
        )));
    };
    Ok(Built {
        image: image.to_string(),
        build_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_size_allows_within_limit() {
        let slot = json!({ "max_bytes": 1000 });
        assert!(check_size(1000, &slot).is_ok());
        assert!(check_size(0, &slot).is_ok());
    }

    #[test]
    fn check_size_refuses_over_limit() {
        let slot = json!({ "max_bytes": 1000 });
        let err = check_size(1001, &slot).unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("exceeds this platform's limit"), "{msg}");
        assert!(msg.contains(".freepodignore"), "{msg}");
    }

    #[test]
    fn terminal_statuses_are_the_three_expected() {
        assert!(TERMINAL_STATUSES.contains(&"succeeded"));
        assert!(TERMINAL_STATUSES.contains(&"failed"));
        assert!(TERMINAL_STATUSES.contains(&"canceled"));
        assert!(!TERMINAL_STATUSES.contains(&"queued"));
        assert!(!TERMINAL_STATUSES.contains(&"building"));
    }
}
