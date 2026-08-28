//! The deploy pipeline: preflight, pack, build, release, and the rollout wait.
//!
//! Mirrors `deploy.py`. The build comes before the deployment is touched, so a
//! first deploy collapses to a single rollout and never shows a placeholder
//! page. Preflight answers every question a cheap read can, cheapest and most
//! fatal first, so a four-minute build is never spent on a deploy a plain GET
//! already knows cannot succeed.

use std::collections::HashMap;
use std::io::Write;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::api::ApiClient;
use crate::config::CUSTOM_PRODUCT_SLUG;
use crate::errors::{freepod, rollout_failed, usage, Error, Result};
use crate::project::{require_project, Project, PROJECT_FILE};
use crate::values::{
    describe_reason, hostname_reasons, is_hostname_property, missing_required,
    normalize_hostname, ApiHostnameChecker, ValueCollector,
};
use crate::{archive, build, tos};

/// Statuses a rollout ends in. `pending` is not among them.
pub const TERMINAL_STATUSES: &[&str] = &["ready", "error"];
/// Statuses the platform accepts an update from.
pub const SETTLED_STATUSES: &[&str] = &["ready", "error"];
/// A deployment that reaches either while we watch it is gone.
const GONE_STATUSES: &[&str] = &["deleting", "deleted"];
pub const STATUS_ERROR: &str = "error";

/// The schema property the built image is delivered through.
pub const IMAGE_KEY: &str = "image";

/// How often to re-read a deployment while waiting.
pub const POLL_SECONDS: f64 = 3.0;

// The `detail` strings the platform's release conflicts carry.
const DETAIL_SCHEMA_INVALID: &str = "product template has an invalid values_schema_json:";
const DETAIL_VALUES_INVALID: &str = "user_values_json is invalid:";
const DETAIL_NOT_READY: &str = "Deployment is not in ready state";
const DETAIL_IN_PROGRESS: &str = "A deployment job is already queued or running";
const DETAIL_DOWNGRADE: &str = "Can only upgrade to newer versions, not downgrade";
const DETAIL_CROSS_PRODUCT: &str = "Upgrade template must belong to the same product";
const DETAIL_NOT_CANONICAL: &str = "Template is not the current canonical for this product";
const DETAIL_DUPLICATE: &str = "Deployment already exists";

/// A write sink for a build log nobody asked to see.
struct Discard;
impl Write for Discard {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        Ok(buf.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// Everything established before a byte is packed.
pub struct Preflight {
    pub project: Project,
    pub user_id: u64,
    pub product: Value,
    pub template: Value,
    pub values: HashMap<String, Value>,
    pub deployment: Option<Value>,
    pub plan: Option<Value>,
}

impl Preflight {
    pub fn template_id(&self) -> u64 {
        self.template.get("id").and_then(|v| v.as_u64()).unwrap_or(0)
    }

    pub fn deployment_template_id(&self) -> Option<u64> {
        self.deployment
            .as_ref()
            .and_then(|d| d.get("desired_template_id"))
            .and_then(|v| v.as_u64())
    }
}

/// Read everything a deploy depends on, cheapest and most fatal first.
pub async fn preflight(
    api: &mut ApiClient,
    env_name: &str,
    root: Option<&Path>,
    recreate: bool,
    interactive: bool,
    echo: &dyn Fn(&str),
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<Preflight> {
    let mut project = require_project(root)?;

    if project.env != env_name && project.deployment_id().is_some() && !recreate {
        return Err(usage(format!(
            "{} records deployment '{}' on '{}', but this command targets '{}'.\n  \
             The deployment would keep running, but this project could no longer address \
             it. Re-run with --recreate to point the project at a new deployment on \
             '{}'.",
            project.path().display(),
            project.deployment_name().unwrap_or(""),
            project.env,
            env_name,
            env_name
        )));
    }

    if recreate && project.deployment_id().is_some() {
        echo(&format!(
            "--recreate: discarding the pointer to deployment '{}' ({}). It is not \
             deleted — if it still exists, it keeps running unattended.",
            project.deployment_name().unwrap_or(""),
            project.deployment_id().unwrap_or("")
        ));
    }

    // `/api/me` first: the reads below are on the edge's skip-auth list and are
    // answered anonymously however bad the credential is.
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    let product = api
        .find_product(CUSTOM_PRODUCT_SLUG)
        .await?
        .ok_or_else(|| {
            freepod(format!(
                "this instance does not offer user-supplied application deployments \
                 ({} publishes no '{CUSTOM_PRODUCT_SLUG}' product).",
                api.env.api_base
            ))
        })?;

    let template = product
        .get("template")
        .cloned()
        .filter(|t| t.get("id").is_some())
        .unwrap_or_else(|| Value::Object(Default::default()));
    if template.get("id").is_none() {
        return Err(freepod(format!(
            "the '{CUSTOM_PRODUCT_SLUG}' product publishes no current template, so \
             there is nothing to deploy against — this is a platform problem, please \
             report it."
        )));
    }

    let schema = template
        .get("values_schema_json")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));
    let properties = schema
        .get("properties")
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();
    if !properties.contains_key(IMAGE_KEY) {
        return Err(freepod(format!(
            "the '{CUSTOM_PRODUCT_SLUG}' product's template {} declares no '{IMAGE_KEY}' \
             value, so a locally built image cannot be delivered to it — this is a \
             platform problem, please report it.",
            template.get("id").and_then(|v| v.as_u64()).unwrap_or(0)
        )));
    }

    // `--recreate` is a decision to abandon the recorded deployment, so its
    // state is not worth a request: whatever it says, this deploy creates.
    let deployment = if recreate {
        None
    } else {
        read_recorded_deployment(api, user_id, &project).await?
    };

    // Both of these are create-only preconditions.
    let mut plan = None;
    if deployment.is_none() {
        plan = Some(select_free_plan(api, &product).await?);
        // Only a create is gated on the terms; an update is not.
        tos::require(api, interactive, echo, ask).await?;
    }

    let values =
        settle_values(api, &mut project, &schema, deployment.as_ref(), interactive, echo).await?;

    Ok(Preflight {
        project,
        user_id,
        product,
        template,
        values,
        deployment,
        plan,
    })
}

/// The recorded deployment, or a refusal naming `--recreate`.
async fn read_recorded_deployment(
    api: &mut ApiClient,
    user_id: u64,
    project: &Project,
) -> Result<Option<Value>> {
    let Some(deployment_id) = project.deployment_id() else {
        return Ok(None);
    };
    let response = api
        .get(&format!("/api/users/{user_id}/deployments/{deployment_id}"), None)
        .await?;
    if response.status == 404 {
        let name = project.deployment_name().map(|n| format!(" ({n})")).unwrap_or_default();
        return Err(freepod(format!(
            "{} points at deployment {deployment_id}{name}, which no longer exists on \
             '{}'.\n  It was deleted outside this project. Run `freepod deploy \
             --recreate` to create a new deployment and re-point {PROJECT_FILE} at it.",
            project.path().display(),
            project.env
        )));
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

/// Fill in whatever the template requires and the file does not carry.
async fn settle_values(
    api: &mut ApiClient,
    project: &mut Project,
    schema: &Value,
    deployment: Option<&Value>,
    interactive: bool,
    echo: &dyn Fn(&str),
) -> Result<HashMap<String, Value>> {
    let mut values = project.user_values.clone();
    let missing = missing_required(schema, &values);
    let hostname_key = hostname_key(schema);

    if !missing.is_empty() {
        echo(&format!(
            "The product template requires {} this project does not carry yet: {}.",
            if missing.len() == 1 { "a value" } else { "values" },
            missing.join(", ")
        ));
        let domains = domains(api).await;
        let checker = Arc::new(ApiHostnameChecker::new(
            api.client().clone(),
            api.env.clone(),
        ));
        let collector = ValueCollector::new(
            schema.clone(),
            domains,
            Some(checker),
            interactive,
        );
        values = collector.collect(&values, true).await?;
        project.user_values = values.clone();
        project.save()?;
    }

    if let Some(key) = hostname_key {
        let current = values
            .get(&key)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let settled = settle_hostname(
            api,
            &current,
            deployment,
            missing.contains(&key),
            echo,
        )
        .await?;
        values.insert(key, Value::String(settled));
    }

    Ok(values)
}

/// Normalize the hostname, and check it only when it is new or changed.
async fn settle_hostname(
    api: &mut ApiClient,
    value: &str,
    deployment: Option<&Value>,
    already_checked: bool,
    echo: &dyn Fn(&str),
) -> Result<String> {
    let domains = if value.contains('.') {
        Vec::new()
    } else {
        domains(api).await
    };
    let fqdn = normalize_hostname(value, &domains);
    let current = deployment
        .and_then(|d| d.get("hostname"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    if already_checked {
        return Ok(fqdn);
    }
    if fqdn.to_lowercase() == current.to_lowercase() {
        return Ok(fqdn);
    }

    let verdict = api.check_hostname(&fqdn).await?;
    if !verdict.get("usable").and_then(|v| v.as_bool()).unwrap_or(false) {
        let reason = verdict.get("reason").and_then(|v| v.as_str());
        return Err(freepod(format!(
            "{fqdn}: {}.\n  Edit 'hostname' in {PROJECT_FILE} and re-run — nothing has \
             been built or deployed.",
            describe_reason(reason)
        )));
    }
    if !current.is_empty() {
        echo(&format!("Hostname {current} → {fqdn}."));
    }
    Ok(fqdn)
}

/// The required property the platform will treat as the hostname, if any.
fn hostname_key(schema: &Value) -> Option<String> {
    let properties = schema.get("properties").and_then(|v| v.as_object())?;
    let required = schema.get("required").and_then(|v| v.as_array())?;
    for name in required.iter().filter_map(|v| v.as_str()) {
        if let Some(spec) = properties.get(name) {
            if is_hostname_property(spec) {
                return Some(name.to_string());
            }
        }
    }
    None
}

/// The platform's wildcard domains, tolerating their absence.
async fn domains(api: &mut ApiClient) -> Vec<String> {
    api.domains().await.unwrap_or_default()
}

/// The first plan whose current template costs nothing.
pub async fn select_free_plan(api: &mut ApiClient, product: &Value) -> Result<Value> {
    let product_id = product.get("id").and_then(|v| v.as_u64()).unwrap_or(0);
    let body = api
        .get_json(&format!("/api/products/{product_id}/plans"), None)
        .await?;
    let plans = body
        .as_array()
        .ok_or_else(|| freepod(format!("unexpected plans response: {body}")))?;
    let slug = product
        .get("slug")
        .and_then(|v| v.as_str())
        .unwrap_or("?")
        .to_string();
    if plans.is_empty() {
        return Err(freepod(format!(
            "the '{slug}' product publishes no plans, so no deployment can be created \
             against it — this is a platform configuration problem, please report it."
        )));
    }

    for plan in plans {
        let template = plan
            .get("template")
            .cloned()
            .unwrap_or_else(|| Value::Object(Default::default()));
        if template.get("price_cents").and_then(|v| v.as_u64()) == Some(0)
            && template.get("id").is_some()
        {
            return Ok(plan.clone());
        }
    }

    let offered = plans
        .iter()
        .filter_map(|p| p.get("name").and_then(|v| v.as_str()))
        .collect::<Vec<_>>()
        .join(", ");
    Err(freepod(format!(
        "the '{slug}' product offers no free plan ({offered}), and this client only \
         supports free plans — a paid plan is created behind a checkout page, which \
         needs the web UI. Nothing has been created."
    )))
}

/// Read a release 409's `detail`. Returns `(message, worth_retrying)`.
pub fn describe_conflict(detail: Option<&str>, move_: Option<&str>) -> (String, bool) {
    let text = detail.unwrap_or("").trim();

    if text.starts_with(DETAIL_SCHEMA_INVALID) {
        return (
            format!(
                "the product template's own values schema is invalid, so nothing can be \
                 deployed against it. This is a platform defect — your configuration \
                 and your values are not at fault, and changing them will not help.\n  \
                 The platform said: {text}\n  Please report it. The built image is \
                 unaffected."
            ),
            false,
        );
    }

    if text.starts_with(DETAIL_VALUES_INVALID) {
        let moved = move_.map(|m| format!(" being moved to ({m})")).unwrap_or_default();
        return (
            format!(
                "the values in {PROJECT_FILE} no longer satisfy the product template\
                 {moved}.\n  The platform said: {text}\n  Retrying cannot help: the \
                 template narrowed what it accepts, so the values have to change. The \
                 build succeeded and is not lost."
            ),
            false,
        );
    }

    if hostname_reasons().contains_key(text) {
        return (
            format!(
                "the hostname was refused: {}.\n  Edit 'hostname' in {PROJECT_FILE} and \
                 re-run.",
                describe_reason(Some(text))
            ),
            false,
        );
    }

    if text == DETAIL_NOT_READY {
        return (
            "the deployment is not in a state that accepts an update — it went back to \
             provisioning between the wait and the release.\n  This is worth retrying \
             in a moment."
                .to_string(),
            true,
        );
    }

    if text == DETAIL_IN_PROGRESS {
        return (
            "another operation on this deployment is already queued or running.\n  This \
             is worth retrying once it finishes."
                .to_string(),
            true,
        );
    }

    if text == DETAIL_DOWNGRADE {
        return (
            "the deployment already runs a newer product template than the one the \
             platform now publishes as current, and templates only move forward.\n  \
             Nothing you can change locally affects this; please report it."
                .to_string(),
            false,
        );
    }

    if text == DETAIL_CROSS_PRODUCT {
        return (
            "the template being moved to belongs to a different product than the \
             deployment does.\n  Nothing you can change locally affects this; please \
             report it."
                .to_string(),
            false,
        );
    }

    if text == DETAIL_NOT_CANONICAL {
        return (
            "the product's current template moved while this deploy was running, so the \
             one it was built against is no longer canonical.\n  Re-running picks up \
             the new template."
                .to_string(),
            true,
        );
    }

    if text == DETAIL_DUPLICATE {
        return (
            format!(
                "a deployment for this account already holds that hostname on that \
                 template.\n  Either point {PROJECT_FILE} at it, or choose a different \
                 hostname."
            ),
            false,
        );
    }

    // Deliberately not guessed at.
    if !text.is_empty() {
        (format!("the platform refused the release: {text}"), false)
    } else {
        (
            "the platform refused the release with a conflict and no explanation."
                .to_string(),
            false,
        )
    }
}

fn conflict(response: &crate::api::ApiResponse, move_: Option<&str>) -> Error {
    let (message, retryable) = describe_conflict(response.detail().as_deref(), move_);
    if retryable {
        freepod(format!("{message}\n  The image is already built; a re-run reuses it."))
    } else {
        freepod(message)
    }
}

/// `4 → 5 (chart custom 0.1.0 → 0.2.0)`, or None when nothing moved.
fn describe_move(from_id: Option<u64>, to_template: &Value) -> Option<String> {
    let from_id = from_id?;
    let to_id = to_template.get("id").and_then(|v| v.as_u64())?;
    if from_id == to_id {
        return None;
    }
    Some(format!("{from_id} → {to_id}"))
}

/// Say that the canonical template moved, rather than moving silently.
fn announce_move(state: &Preflight, echo: &dyn Fn(&str)) -> Option<String> {
    let move_ = describe_move(state.deployment_template_id(), &state.template)?;
    let was = state
        .deployment
        .as_ref()?
        .get("desired_template")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));
    let now = &state.template;
    let mut detail = String::new();
    let was_chart = was.get("chart_version").and_then(|v| v.as_str());
    let now_chart = now.get("chart_version").and_then(|v| v.as_str());
    if let (Some(wc), Some(nc)) = (was_chart, now_chart) {
        if !wc.is_empty() && wc != nc {
            let chart_ref = now.get("chart_ref").and_then(|v| v.as_str()).unwrap_or("");
            let chart = chart_ref.rsplit('/').next().unwrap_or("");
            detail = format!(" (chart {chart} {wc} → {nc})");
        }
    }
    echo(&format!("Product template {move_}{detail}."));
    Some(move_)
}

/// `POST /api/users/{user_id}/deployments` — one rollout, image included.
pub async fn create_deployment(
    api: &mut ApiClient,
    user_id: u64,
    template_id: u64,
    plan_template_id: u64,
    values: &HashMap<String, Value>,
    build_id: Option<&str>,
) -> Result<Value> {
    let mut body = json!({
        "desired_template_id": template_id,
        "plan_template_id": plan_template_id,
        "user_values_json": values,
    });
    if let Some(bid) = build_id {
        body["build_id"] = json!(bid);
    }
    let response = api
        .post_json(&format!("/api/users/{user_id}/deployments"), Some(&body))
        .await?;
    if response.status == 409 {
        return Err(conflict(&response, None));
    }
    if response.status == 400 && response.detail().as_deref() == Some(tos::DEPLOY_REFUSAL) {
        return Err(freepod(format!(
            "the platform refused the deployment because this account has not accepted \
             its terms.\n  Run `freepod login --env {}` to accept them, or accept them \
             at {}, then re-run.\n  The build succeeded and is not lost.",
            api.env.name, api.env.api_base
        )));
    }
    if response.status != 201 {
        return Err(freepod(format!(
            "could not create the deployment: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }

    let envelope = response.decode()?;
    if envelope
        .get("checkout_url")
        .filter(|v| !v.is_null())
        .is_some()
    {
        return Err(freepod(
            "the platform returned a checkout page for this deployment, which means \
             the selected plan is not free. This client only supports free plans; \
             finish or cancel the deployment in the web UI.",
        ));
    }
    envelope
        .get("deployment")
        .cloned()
        .ok_or_else(|| freepod(format!("unexpected create response: {envelope}")))
}

/// `PUT` the same route, with the complete user-values document.
pub async fn update_deployment(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    template_id: u64,
    values: &HashMap<String, Value>,
    move_: Option<&str>,
    build_id: Option<&str>,
) -> Result<Value> {
    let mut body = json!({
        "desired_template_id": template_id,
        "user_values_json": values,
    });
    if let Some(bid) = build_id {
        body["build_id"] = json!(bid);
    }
    let response = api
        .put_json(
            &format!("/api/users/{user_id}/deployments/{deployment_id}"),
            Some(&body),
        )
        .await?;
    if response.status == 409 {
        return Err(conflict(&response, move_));
    }
    if !response.is_success() {
        return Err(freepod(format!(
            "could not update the deployment: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    response.decode()
}

/// The deployment, or a failure if it disappeared while we watched.
pub async fn read_deployment(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
) -> Result<Value> {
    let response = api
        .get(&format!("/api/users/{user_id}/deployments/{deployment_id}"), None)
        .await?;
    if response.status == 404 {
        return Err(freepod(format!(
            "deployment {deployment_id} disappeared while this deploy was running — it \
             was deleted from elsewhere."
        )));
    }
    if !response.is_success() {
        return Err(freepod(format!(
            "could not read deployment {deployment_id}: HTTP {} {}",
            response.status,
            response.text().trim().chars().take(300).collect::<String>()
        )));
    }
    response.decode()
}

/// Wait until the deployment is in a state the platform accepts an update from.
pub async fn wait_until_settled(
    api: &mut ApiClient,
    user_id: u64,
    deployment: Value,
    timeout: u64,
    poll: f64,
    echo: &dyn Fn(&str),
) -> Result<Value> {
    if deployment
        .get("status")
        .and_then(|v| v.as_str())
        .map(|s| SETTLED_STATUSES.contains(&s))
        .unwrap_or(false)
    {
        return Ok(deployment);
    }

    let deployment_id = deployment
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let mut reported: Option<String> = None;
    let deadline = Instant::now() + Duration::from_secs(timeout);
    let mut deployment = deployment;

    loop {
        let status = deployment
            .get("status")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        if SETTLED_STATUSES.contains(&status.as_str()) {
            return Ok(deployment);
        }
        if GONE_STATUSES.contains(&status.as_str()) {
            return Err(freepod(format!(
                "the deployment is {status} and cannot be updated. Run `freepod deploy \
                 --recreate` to create a new one."
            )));
        }
        if reported.as_deref() != Some(status.as_str()) {
            echo(&format!(
                "  Waiting for the deployment to settle (currently {status})..."
            ));
            reported = Some(status.clone());
        }
        if Instant::now() >= deadline {
            return Err(freepod(format!(
                "stopped waiting after {timeout}s for deployment {deployment_id} to \
                 leave '{status}'. It is still rolling out on the platform; nothing was \
                 canceled. The built image is not lost — re-run to release it."
            )));
        }
        tokio::time::sleep(Duration::from_secs_f64(poll)).await;
        deployment = read_deployment(api, user_id, &deployment_id).await?;
    }
}

/// Poll until *our* rollout is terminal, not merely until one is.
pub async fn follow_rollout(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    generation: u64,
    timeout: u64,
    poll: f64,
    echo: &dyn Fn(&str),
) -> Result<Value> {
    let mut reported: Option<String> = None;
    let deadline = Instant::now() + Duration::from_secs(timeout);

    loop {
        let record = read_deployment(api, user_id, deployment_id).await?;
        let status = record
            .get("status")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let current = record.get("generation").and_then(|v| v.as_u64()).unwrap_or(0);

        if current >= generation && TERMINAL_STATUSES.contains(&status.as_str()) {
            return Ok(record);
        }
        if GONE_STATUSES.contains(&status.as_str()) {
            return Err(freepod(format!(
                "deployment {deployment_id} became '{status}' during the rollout — it \
                 was deleted from elsewhere."
            )));
        }

        if reported.as_deref() != Some(status.as_str()) {
            echo(&format!("  {status}..."));
            reported = Some(status.clone());
        }

        if Instant::now() >= deadline {
            return Err(freepod(format!(
                "stopped waiting after {timeout}s. Deployment {deployment_id} is still \
                 rolling out on the platform — it was not canceled. Check it with \
                 `freepod deploy` again, or in the web UI."
            )));
        }
        tokio::time::sleep(Duration::from_secs_f64(poll)).await;
    }
}

/// `https://…` for a deployment's hostname, or None.
pub fn address(deployment: &Value) -> Option<String> {
    deployment
        .get("hostname")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|h| format!("https://{h}"))
}

/// Create or update the deployment, then follow the rollout. Returns the address.
pub async fn release(
    api: &mut ApiClient,
    state: &mut Preflight,
    image: &str,
    build_id: Option<&str>,
    timeout: u64,
    poll: f64,
    echo: &dyn Fn(&str),
) -> Result<String> {
    let mut values = state.values.clone();
    values.insert(IMAGE_KEY.to_string(), Value::String(image.to_string()));

    let record = if state.deployment.is_none() {
        let plan = match state.plan.clone() {
            Some(p) => p,
            None => select_free_plan(api, &state.product).await?,
        };
        let plan_name = plan.get("name").and_then(|v| v.as_str()).unwrap_or("?");
        echo(&format!("Creating a deployment on the '{plan_name}' plan..."));
        let plan_template_id = plan
            .get("template")
            .and_then(|t| t.get("id"))
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        let record = create_deployment(
            api,
            state.user_id,
            state.template_id(),
            plan_template_id,
            &values,
            build_id,
        )
        .await?;
        // Written before the rollout is awaited: a deployment that exists but is
        // not recorded is one this project can never address again.
        if state.project.env != api.env.name {
            state.project.env = api.env.name.to_string();
        }
        let rec_id = record.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let rec_name = record.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string();
        state.project.record_deployment(rec_id.clone(), rec_name.clone())?;
        echo(&format!("Created deployment '{rec_name}' ({rec_id})."));
        record
    } else {
        let settled = wait_until_settled(
            api,
            state.user_id,
            state.deployment.clone().unwrap(),
            timeout,
            poll,
            echo,
        )
        .await?;
        let move_ = announce_move(state, echo);
        let settled_name = settled.get("name").and_then(|v| v.as_str()).unwrap_or("?");
        echo(&format!("Releasing to deployment '{settled_name}'..."));
        let settled_id = settled.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
        update_deployment(
            api,
            state.user_id,
            &settled_id,
            state.template_id(),
            &values,
            move_.as_deref(),
            build_id,
        )
        .await?
    };

    let record_id = record.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let generation = record.get("generation").and_then(|v| v.as_u64()).unwrap_or(0);
    let final_ =
        follow_rollout(api, state.user_id, &record_id, generation, timeout, poll, echo).await?;

    if final_.get("status").and_then(|v| v.as_str()) == Some(STATUS_ERROR) {
        let name = final_.get("name").and_then(|v| v.as_str()).unwrap_or("?");
        let id = final_.get("id").and_then(|v| v.as_str()).unwrap_or("?");
        let last_error = final_
            .get("last_error")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .unwrap_or("no error message");
        return Err(rollout_failed(format!(
            "the rollout failed for deployment {name} ({id}).\n  The platform recorded: \
             {last_error}"
        )));
    }

    let id = final_.get("id").and_then(|v| v.as_str()).unwrap_or("?");
    address(&final_).ok_or_else(|| {
        freepod(format!(
            "deployment {id} is ready but carries no hostname — this is an unexpected \
             platform condition, please report it."
        ))
    })
}

/// Report configuration this rollout will apply along with the code.
pub async fn announce_pending_vars(
    api: &mut ApiClient,
    state: &Preflight,
    echo: &dyn Fn(&str),
) -> Result<()> {
    let Some(deployment) = state.deployment.as_ref() else {
        return Ok(());
    };
    if !deployment
        .get("pending")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
        return Ok(());
    }
    let count = pending_count(api, state.user_id, deployment).await?;
    match count {
        None => echo("This rollout will also apply some pending vars."),
        Some(0) => {}
        Some(n) => {
            let subject = if n == 1 { "var" } else { "vars" };
            echo(&format!("This rollout will also apply {n} pending {subject}."));
        }
    }
    Ok(())
}

/// How many vars a rollout would change, or None if it cannot be told.
async fn pending_count(
    api: &mut ApiClient,
    user_id: u64,
    deployment: &Value,
) -> Result<Option<u64>> {
    if !deployment
        .get("pending")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
        return Ok(Some(0));
    }
    let head = deployment
        .get("vars")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));
    let applied = deployment
        .get("applied_release")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));
    let Some(number) = applied.get("number").and_then(|v| v.as_u64()) else {
        return Ok(head.as_object().map(|o| o.len() as u64));
    };
    let deployment_id = deployment.get("id").and_then(|v| v.as_str()).unwrap_or("");
    let path = format!(
        "/api/users/{user_id}/deployments/{deployment_id}/releases/{number}"
    );
    let response = api.get(&path, None).await?;
    if !response.is_success() {
        return Ok(None);
    }
    let running_doc = response.decode()?;
    let running = running_doc
        .get("vars")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));

    let changed = changed_count(
        head.as_object().unwrap(),
        running.as_object().unwrap(),
    );
    Ok(Some(changed))
}

/// How many vars differ between the deployment's head and the release it is
/// running. A key present on only one side differs — that is what changed.
fn changed_count(
    head: &serde_json::Map<String, Value>,
    running: &serde_json::Map<String, Value>,
) -> u64 {
    let mut keys: Vec<&str> = head.keys().map(|s| s.as_str()).collect();
    for k in running.keys() {
        if !keys.contains(&k.as_str()) {
            keys.push(k.as_str());
        }
    }
    keys.iter()
        .copied()
        .filter(|k| entry(head.get(*k)) != entry(running.get(*k)))
        .count() as u64
}

/// A var's comparable identity: value, sensitivity, and when it last changed.
/// Absent (or not an object) is its own value.
fn entry(v: Option<&Value>) -> Option<(Option<String>, Option<bool>, Option<String>)> {
    let v = v.filter(|v| v.is_object())?;
    Some((
        v.get("value").and_then(|x| x.as_str()).map(|s| s.to_string()),
        v.get("sensitive").and_then(|x| x.as_bool()),
        v.get("updated_at").and_then(|x| x.as_str()).map(|s| s.to_string()),
    ))
}

/// The image the deployment is running, and the build that produced it.
pub fn applied_image(deployment: &Value) -> (Option<String>, Option<String>) {
    let applied = deployment
        .get("applied_release")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));
    let values = applied
        .get("values_json")
        .cloned()
        .filter(|v| v.is_object())
        .unwrap_or_else(|| Value::Object(Default::default()));
    let image = values
        .get(IMAGE_KEY)
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());
    let build_id = applied
        .get("build_id")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());
    (image, build_id)
}

/// Roll the deployment again on the image it already runs. Returns the address.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
pub async fn release_current(
    api: &mut ApiClient,
    env_name: &str,
    root: Option<&Path>,
    interactive: bool,
    timeout: u64,
    poll: f64,
    echo: &dyn Fn(&str),
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<String> {
    let mut state = preflight(api, env_name, root, false, interactive, echo, ask).await?;
    if state.deployment.is_none() {
        return Err(freepod(
            "this project has no deployment yet, so there is nothing to roll.\n  Run \
             `freepod deploy` to create one.",
        ));
    }
    let (image, build_id) = applied_image(state.deployment.as_ref().unwrap());
    let Some(image) = image else {
        let name = state
            .deployment
            .as_ref()
            .unwrap()
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("?");
        return Err(freepod(format!(
            "deployment '{name}' has never completed a rollout, so there is no image \
             to release.\n  Run `freepod deploy` to build and release one."
        )));
    };
    announce_pending_vars(api, &state, echo).await?;
    echo(&format!("Releasing {image} again."));
    release(api, &mut state, &image, build_id.as_deref(), timeout, poll, echo).await
}

/// Preflight, pack, upload, build, release. Returns the live address.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
pub async fn deploy(
    api: &mut ApiClient,
    env_name: &str,
    root: Option<&Path>,
    recreate: bool,
    honor_gitignore: bool,
    interactive: bool,
    verbose: bool,
    quiet: bool,
    build_timeout: u64,
    rollout_timeout: u64,
    poll: f64,
    ask: &dyn Fn(&str) -> Result<bool>,
) -> Result<String> {
    let echo = |m: &str| {
        if !quiet {
            eprintln!("{m}");
        }
    };
    let mut state =
        preflight(api, env_name, root, recreate, interactive, &echo, ask).await?;
    announce_pending_vars(api, &state, &echo).await?;

    let on_skip: crate::archive::SkipHook = if quiet {
        None
    } else {
        Some(Box::new(|name, reason| eprintln!("  skipped {name}: {reason}")))
    };
    let (archive, size, members) = archive::pack(&state.project.root, honor_gitignore, on_skip)
        .map_err(|e| freepod(format!("could not pack the project: {e}")))?;
    if !quiet {
        archive::report(size, &members, verbose, &echo);
    }

    let store = crate::api::http_client();
    let mut out: Box<dyn Write + Unpin> = if quiet {
        Box::new(Discard)
    } else {
        Box::new(std::io::stderr())
    };
    let built = build::build_image(
        api,
        state.user_id,
        &archive,
        size,
        &store,
        &mut out,
        build_timeout,
        quiet,
        &echo,
    )
    .await?;
    echo(&format!("Built {}.", built.image));

    release(
        api,
        &mut state,
        &built.image,
        Some(&built.build_id),
        rollout_timeout,
        poll,
        &echo,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn conflict_is_retryable_only_for_the_known_transient_details() {
        assert!(describe_conflict(Some(DETAIL_NOT_READY), None).1);
        assert!(describe_conflict(Some(DETAIL_IN_PROGRESS), None).1);
        assert!(describe_conflict(Some(DETAIL_NOT_CANONICAL), None).1);
        assert!(!describe_conflict(Some(DETAIL_SCHEMA_INVALID), None).1);
        assert!(!describe_conflict(Some(DETAIL_DUPLICATE), None).1);
        assert!(!describe_conflict(Some("something unrecognized"), None).1);
        assert!(!describe_conflict(None, None).1);
    }

    #[test]
    fn values_invalid_carries_the_move() {
        let (msg, retryable) = describe_conflict(Some(DETAIL_VALUES_INVALID), Some("4 → 5"));
        assert!(!retryable);
        assert!(msg.contains("being moved to (4 → 5)"), "{msg}");
    }

    #[test]
    fn hostname_reason_is_named() {
        let (msg, retryable) = describe_conflict(Some("in_use"), None);
        assert!(!retryable);
        assert!(msg.contains("the hostname was refused"), "{msg}");
        assert!(msg.contains("already taken"), "{msg}");
    }

    #[test]
    fn address_uses_https() {
        let d = json!({ "hostname": "foo.freepod.eu" });
        assert_eq!(address(&d).as_deref(), Some("https://foo.freepod.eu"));
        assert_eq!(address(&json!({})), None);
        assert_eq!(address(&json!({ "hostname": "" })), None);
    }

    #[test]
    fn applied_image_reads_the_applied_release() {
        let d = json!({
            "applied_release": {
                "values_json": { "image": "reg/app@sha256:abc" },
                "build_id": "b1"
            }
        });
        assert_eq!(applied_image(&d), (Some("reg/app@sha256:abc".into()), Some("b1".into())));
        assert_eq!(applied_image(&json!({})), (None, None));
    }

    #[test]
    fn describe_move_reports_only_when_changed() {
        assert_eq!(describe_move(Some(4), &json!({ "id": 5 })).as_deref(), Some("4 → 5"));
        assert_eq!(describe_move(Some(4), &json!({ "id": 4 })), None);
        assert_eq!(describe_move(None, &json!({ "id": 5 })), None);
    }

    #[test]
    fn changed_count_counts_keys_on_only_one_side() {
        let head = json!({
            "A": { "value": "1", "updated_at": "t1" },
            "B": { "value": "2", "updated_at": "t2" }
        })
        .as_object()
        .unwrap()
        .clone();
        let running = json!({
            "A": { "value": "1", "updated_at": "t1" }
        })
        .as_object()
        .unwrap()
        .clone();
        // B is new, A is unchanged: one change.
        assert_eq!(changed_count(&head, &running), 1);
        // The same keys in the other direction: still one change.
        assert_eq!(changed_count(&running, &head), 1);
        // A rewritten value is a change even with the same key on both sides.
        let mut head2 = head.clone();
        head2.insert("A".into(), json!({ "value": "9", "updated_at": "t9" }));
        assert_eq!(changed_count(&head2, &running), 2);
        // Identical maps: no change.
        assert_eq!(changed_count(&head, &head), 0);
    }
}
