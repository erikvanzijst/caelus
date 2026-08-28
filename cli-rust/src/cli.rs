//! The command-line interface: argument parsing, the shared context, and the
//! per-command handlers. Mirrors `cli.py`.
//!
//! Stream discipline: results go to stdout, everything else to stderr, so a
//! piped stdout carries only the result.

use std::collections::HashMap;
use std::io::{IsTerminal, Write};
use std::sync::Arc;

use clap::{CommandFactory, Parser, Subcommand};
use serde_json::Value;

use crate::api::{http_client, ApiClient};
use crate::auth::{format_claims, forget_environment, Session};
use crate::config::{
    cache_path_hint, environment_names, resolve_environment, wait_seconds,
    BUILD_WAIT_SECONDS, CUSTOM_PRODUCT_SLUG, DEFAULT_HTTP_TIMEOUT, LOGIN_WAIT_SECONDS,
    ROLLOUT_WAIT_SECONDS,
};
use crate::errors::{freepod, usage, Error, Result};
use crate::project::{self, PROJECT_FILE};
use crate::values::{ApiHostnameChecker, ValueCollector};
use crate::{prompt, tos};

#[derive(Parser)]
#[command(
    name = "freepod",
    version,
    about = "Take a local project directory to a running Freepod deployment."
)]
struct Cli {
    /// target environment: dev, prod (default: the environment recorded in
    /// .freepod-rust.json, else FREEPOD_ENV, else prod)
    #[arg(long, value_name = "NAME", global = true)]
    env: Option<String>,

    /// show extra detail, including token claims
    #[arg(long, global = true)]
    verbose: bool,

    /// suppress progress and diagnostics; results and errors still appear
    #[arg(long, global = true)]
    quiet: bool,

    /// override the wait for whichever operation is in progress
    #[arg(long, value_name = "SECONDS", global = true)]
    timeout: Option<u64>,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Authenticate against Freepod and cache the credential.
    Login {
        /// force the browser flow
        #[arg(long)]
        loopback: bool,
        /// force the device flow
        #[arg(long)]
        device: bool,
        /// ignore any cached credential and re-authenticate
        #[arg(long)]
        force: bool,
    },
    /// Discard the cached credential for the selected environment.
    Logout,
    /// Report who the cached credential authenticates as.
    Whoami,
    /// Set up the current directory as a Freepod project.
    Init {
        /// overwrite an existing .freepod-rust.json, discarding its deployment pointer
        #[arg(long)]
        force: bool,
    },
    /// Build the current project and release it to its deployment.
    Deploy {
        /// discard the recorded deployment pointer and create a new deployment
        #[arg(long)]
        recreate: bool,
        /// pack the tree without applying .gitignore rules
        #[arg(long)]
        no_gitignore: bool,
        /// release the image already running, without packing or building
        #[arg(long)]
        no_build: bool,
    },
    /// Delete this project's deployment and everything it stores.
    Delete {
        /// skip the confirmation prompt — the only way to delete unattended
        #[arg(long, short = 'y')]
        yes: bool,
        /// return once the teardown is scheduled instead of following it
        #[arg(long)]
        no_wait: bool,
    },
    /// List this account's builds, most recent first.
    Builds {
        /// how many builds to show (default: 20)
        #[arg(long, value_name = "N")]
        limit: Option<u64>,
        /// show every build, ignoring --limit
        #[arg(long)]
        all: bool,
    },
    /// List this project's deployment's releases, most recent first.
    Releases {
        /// how many releases to show (default: 20)
        #[arg(long, value_name = "N")]
        limit: Option<u64>,
        /// show every release, ignoring --limit
        #[arg(long)]
        all: bool,
    },
    /// Read and change the environment your application runs with.
    Var {
        #[command(subcommand)]
        command: VarCommands,
    },
    /// Stream this project's application output.
    Log {
        /// keep the stream open and print lines as they arrive
        #[arg(short = 'f', long = "follow")]
        follow: bool,
        /// how many trailing lines to start with (default: the platform's)
        #[arg(short = 'n', long = "tail", value_name = "LINES")]
        tail: Option<u64>,
        /// pin to one release by its number, including one that failed and was rolled back
        #[arg(short = 'r', long = "release", value_name = "NUMBER")]
        release: Option<u64>,
        /// prefix each line with the time the platform recorded for it
        #[arg(short = 't', long = "timestamps")]
        timestamps: bool,
    },
    /// Install the deployment instructions for your coding agents.
    Skill {
        #[command(subcommand)]
        command: SkillCommands,
    },
}

#[derive(Subcommand)]
enum VarCommands {
    /// List this deployment's vars.
    List {
        /// emit the platform's wire shape
        #[arg(long)]
        json: bool,
    },
    /// Print one var's value.
    Get {
        key: String,
    },
    /// Set vars and roll the deployment so they take effect.
    Set {
        /// KEY=VALUE pairs; a bare KEY is prompted for without echo
        #[arg(value_name = "ASSIGNMENT")]
        assignments: Vec<String>,
        /// store these vars write-only
        #[arg(long)]
        secret: bool,
        /// read vars from FILE (wire shape or KEY=VALUE lines); '-' is stdin
        #[arg(short = 'f', long = "file", value_name = "FILE")]
        source: Option<String>,
        /// record the vars without rolling the deployment
        #[arg(long)]
        stage: bool,
    },
    /// Remove vars and roll the deployment.
    Rm {
        /// the keys to remove
        #[arg(required = true, value_name = "KEY")]
        keys: Vec<String>,
        /// record the removal without rolling the deployment
        #[arg(long)]
        stage: bool,
    },
}

#[derive(Subcommand)]
enum SkillCommands {
    /// Write the packaged skill where a coding agent will find it.
    Install {
        /// install for this agent whether or not it is detected; repeatable
        #[arg(long, value_name = "NAME")]
        agent: Vec<String>,
        /// install for every supported agent
        #[arg(long)]
        all: bool,
        /// install into this directory's per-agent skill folders rather than the home directory
        #[arg(long)]
        project: bool,
        /// write SKILL.md to this exact path instead, for an agent not listed
        #[arg(long, value_name = "PATH")]
        dest: Option<std::path::PathBuf>,
    },
    /// Print the packaged skill to stdout.
    Show,
}

/// What every command needs: which environment, and how loud to be.
struct Context {
    env: crate::config::Environment,
    verbose: bool,
    quiet: bool,
    timeout: Option<u64>,
    http: reqwest::Client,
}

impl Context {
    fn new(
        env_name: Option<&str>,
        verbose: bool,
        quiet: bool,
        timeout: Option<u64>,
    ) -> Result<Self> {
        // An explicit --env outranks the project file; without one, a project
        // in this directory decides where the command goes.
        let project_env = if env_name.is_some() {
            None
        } else {
            declared_environment()
        };
        let env = resolve_environment(env_name, project_env.as_deref())?;
        Ok(Self {
            env,
            verbose,
            quiet,
            timeout,
            http: http_client(),
        })
    }

    /// Diagnostics, unless silenced. Never the result.
    fn say(&self, message: &str) {
        if !self.quiet {
            eprintln!("{message}");
        }
    }

    fn session(&self, force_flow: Option<String>) -> Result<Session> {
        let timeout = wait_seconds(self.timeout, LOGIN_WAIT_SECONDS)?;
        Ok(Session::new(self.env.clone(), timeout, force_flow, self.verbose))
    }

    fn client(&self, session: Session) -> ApiClient {
        ApiClient::with_client(
            self.env.clone(),
            session,
            DEFAULT_HTTP_TIMEOUT,
            self.http.clone(),
        )
    }
}

/// The environment this directory's project declares, or None.
///
/// Best-effort: it runs for every command, including ones with no business in
/// the project. A missing file yields None, and a broken one does too — the
/// command that needs the project loads it itself and reports the real problem.
fn declared_environment() -> Option<String> {
    let root = project::find_project_root(None)?;
    let name = project::load(&root).ok()?.env;
    if crate::config::environments().contains_key(name.as_str()) {
        Some(name)
    } else {
        None
    }
}

/// Run the CLI and map every failure onto its exit code.
pub fn run() -> i32 {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("failed to build the async runtime");
    runtime.block_on(async_main())
}

async fn async_main() -> i32 {
    let cli = Cli::parse();

    if cli.verbose && cli.quiet {
        return handle_error(usage(
            "--verbose and --quiet contradict each other; pick one",
        ));
    }
    // An unset shell variable expands to this. Falling through to the default
    // would deploy to prod on the strength of a variable the script believed it
    // had set, which is the one outcome an explicit --env must never produce.
    if let Some(name) = &cli.env {
        if name.trim().is_empty() {
            return handle_error(usage(format!(
                "--env was given an empty value — name one of {}, or omit it to use \
                 the environment recorded in {PROJECT_FILE}",
                environment_names()
            )));
        }
    }

    let ctx = match Context::new(cli.env.as_deref(), cli.verbose, cli.quiet, cli.timeout) {
        Ok(c) => c,
        Err(e) => return handle_error(e),
    };

    let outcome = match &cli.command {
        None => {
            let mut out = std::io::stdout();
            let _ = Cli::command().write_help(&mut out);
            let _ = writeln!(out);
            Ok(0)
        }
        Some(Commands::Login {
            loopback,
            device,
            force,
        }) => {
            let flow = match (*loopback, *device) {
                (true, true) => {
                    return handle_error(usage(
                        "--loopback and --device both force a flow; pick one",
                    ))
                }
                (true, false) => Some("loopback".to_string()),
                (false, true) => Some("device".to_string()),
                _ => None,
            };
            cmd_login(&ctx, flow, *force).await
        }
        Some(Commands::Logout) => cmd_logout(&ctx).await,
        Some(Commands::Whoami) => cmd_whoami(&ctx).await,
        Some(Commands::Init { force }) => cmd_init(&ctx, *force).await,
        Some(Commands::Deploy {
            recreate,
            no_gitignore,
            no_build,
        }) => cmd_deploy(&ctx, *recreate, *no_gitignore, *no_build).await,
        Some(Commands::Delete { yes, no_wait }) => cmd_delete(&ctx, *yes, *no_wait).await,
        Some(Commands::Builds { limit, all }) => {
            cmd_builds(&ctx, limit.unwrap_or(crate::history::DEFAULT_LIMIT as u64), *all).await
        }
        Some(Commands::Releases { limit, all }) => {
            cmd_releases(&ctx, limit.unwrap_or(crate::releases::DEFAULT_LIMIT as u64), *all)
                .await
        }
        Some(Commands::Var { command }) => match command {
            VarCommands::List { json } => cmd_var_list(&ctx, *json).await,
            VarCommands::Get { key } => cmd_var_get(&ctx, key).await,
            VarCommands::Set {
                assignments,
                secret,
                source,
                stage,
            } => {
                cmd_var_set(
                    &ctx,
                    assignments,
                    *secret,
                    source.as_deref(),
                    *stage,
                )
                .await
            }
            VarCommands::Rm { keys, stage } => cmd_var_rm(&ctx, keys, *stage).await,
        },
        Some(Commands::Log {
            follow,
            tail,
            release,
            timestamps,
        }) => {
            cmd_log(&ctx, *follow, *tail, *release, *timestamps).await
        }
        Some(Commands::Skill { command }) => match command {
            SkillCommands::Install {
                agent,
                all,
                project,
                dest,
            } => {
                cmd_skill_install(
                    &ctx,
                    agent,
                    *all,
                    *project,
                    dest.as_deref(),
                )
                .await
            }
            SkillCommands::Show => cmd_skill_show(&ctx).await,
        },
    };

    match outcome {
        Ok(code) => code,
        Err(e) => handle_error(e),
    }
}

/// Print the error and return its exit code. Usage errors carry no leading
/// newline; every other row does.
fn handle_error(e: Error) -> i32 {
    let prefix = if matches!(e, Error::Usage(_)) { "" } else { "\n" };
    eprintln!("{prefix}error: {}", e.message());
    e.exit_code()
}

// --------------------------------------------------------------------------
// Commands
// --------------------------------------------------------------------------

async fn cmd_login(ctx: &Context, flow: Option<String>, force: bool) -> Result<i32> {
    let mut session = ctx.session(flow)?;
    session.authenticate(&ctx.http, force, true).await?;
    let flow_used = session
        .flow_used
        .clone()
        .unwrap_or_else(|| "none — reused a cached credential".to_string());
    let credential_source = session.credential_source.clone();
    let access_token = session.access_token.clone();
    let mut api = ctx.client(session);
    let me = api.me().await?;
    let email = me.get("email").and_then(|v| v.as_str()).unwrap_or("?");
    let id = me.get("id").and_then(|v| v.as_u64()).unwrap_or(0);

    ctx.say(&format!(
        "Authenticated as {email} (user id {id}) on '{}'.",
        ctx.env.name
    ));
    ctx.say(&format!("  flow       : {flow_used}"));
    ctx.say(&format!("  credential : {credential_source}"));
    if ctx.verbose {
        if let Some(token) = &access_token {
            ctx.say(&format_claims(token));
        }
    }

    // Offered, never required. `login` is also how a headless box and a CI job
    // get a credential; refusing to finish over an unaccepted agreement would
    // break all three for a fact only `deploy` actually needs.
    let interactive = std::io::stdin().is_terminal();
    let status = tos::settle(
        &mut api,
        interactive,
        &|m| ctx.say(m),
        &|q| prompt::confirm(q, false),
    )
    .await?;
    if status == tos::VERSION_UNKNOWN {
        ctx.say(&format!(
            "  terms      : not accepted — accept them at {}.",
            ctx.env.api_base
        ));
    } else if status != tos::ACCEPTED {
        ctx.say(
            "  terms      : not accepted — `freepod deploy` will ask before \
             creating your first deployment.",
        );
    }
    Ok(0)
}

async fn cmd_logout(ctx: &Context) -> Result<i32> {
    let name = ctx.env.name;
    if forget_environment(name) {
        ctx.say(&format!(
            "Discarded the cached credential for '{name}' from {}.",
            cache_path_hint()
        ));
    } else {
        ctx.say(&format!(
            "No cached credential for '{name}' in {}.",
            cache_path_hint()
        ));
    }
    ctx.say(
        "Note: this only forgets the local copy. The credential remains valid on \
         the platform until it is revoked there — use the Keycloak account console \
         (Applications -> offline sessions).",
    );
    Ok(0)
}

async fn cmd_whoami(ctx: &Context) -> Result<i32> {
    let mut session = ctx.session(None)?;
    // Never start a login from `whoami`: a command that merely reports identity
    // should say "not authenticated" rather than opening a browser.
    session.authenticate(&ctx.http, false, false).await?;
    let access_token = session.access_token.clone();
    let mut api = ctx.client(session);
    let me = api.me().await?;
    let email = me.get("email").and_then(|v| v.as_str()).unwrap_or("?");
    let id = me.get("id").and_then(|v| v.as_u64()).unwrap_or(0);

    println!("{email}");
    println!("user id: {id}");
    if me.get("is_admin").and_then(|v| v.as_bool()).unwrap_or(false) {
        println!("admin:   yes");
    }
    ctx.say(&format!(
        "Environment '{}' ({}).",
        ctx.env.name, ctx.env.api_base
    ));
    if ctx.verbose {
        if let Some(token) = &access_token {
            ctx.say(&format_claims(token));
        }
    }
    Ok(0)
}

async fn cmd_init(ctx: &Context, force: bool) -> Result<i32> {
    let root = std::env::current_dir()
        .map_err(|e| freepod(format!("cannot determine the current directory: {e}")))?;
    let target = root.join(PROJECT_FILE);

    if target.exists() && !force {
        return Err(usage(format!(
            "{} already exists. Re-run with --force to discard it and start over — \
             note that this also discards the deployment pointer, so the existing \
             deployment would be orphaned.\n  To change a value, edit {PROJECT_FILE} \
             directly; `freepod deploy` asks for anything required that is missing.",
            target.display()
        )));
    }
    if target.exists() && force {
        if let Ok(existing) = project::load(&root) {
            if let Some(name) = existing.deployment_name() {
                ctx.say(&format!(
                    "Warning: --force discards the pointer to deployment '{name}'. It \
                     will keep running, and this project will no longer be able to \
                     update it."
                ));
            }
        }
    }

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);

    // `/api/me` first: everything else init reads is public and would be
    // answered anonymously however bad the credential is.
    api.me().await?;

    let Some(product) = api.find_product(CUSTOM_PRODUCT_SLUG).await? else {
        return Err(freepod(format!(
            "this instance does not offer user-supplied application deployments \
             ({} publishes no '{CUSTOM_PRODUCT_SLUG}' product).",
            ctx.env.api_base
        )));
    };
    let template = product
        .get("template")
        .cloned()
        .unwrap_or(Value::Object(Default::default()));
    let schema = template
        .get("values_schema_json")
        .cloned()
        .unwrap_or(Value::Object(Default::default()));
    if schema.get("properties").is_none() {
        return Err(freepod(format!(
            "the '{CUSTOM_PRODUCT_SLUG}' product's template declares no user values \
             schema, so there is nothing to configure — this is a platform problem, \
             please report it."
        )));
    }
    let product_name = product.get("name").and_then(|v| v.as_str()).unwrap_or("?");
    // The template id is an integer on the wire; `value_str` renders it as
    // digits the way the Python client's `str()` did.
    let template_id = template
        .get("id")
        .map(crate::table::value_str)
        .unwrap_or_else(|| "?".to_string());
    ctx.say(&format!("Product '{product_name}' (template {template_id})."));

    let domains = api.domains().await?;
    let checker = Arc::new(ApiHostnameChecker::new(ctx.http.clone(), ctx.env.clone()));
    let interactive = std::io::stdin().is_terminal();
    let collector = ValueCollector::new(schema, domains, Some(checker), interactive);
    let values = collector.collect(&HashMap::new(), false).await?;

    let new = project::Project::new(root, ctx.env.name, values);
    new.save()?;

    // The path is the result; everything else is commentary.
    println!("{}", target.display());
    ctx.say(&format!(
        "Initialized for '{}'. Run `freepod deploy` to build and release.",
        ctx.env.name
    ));
    Ok(0)
}

async fn cmd_deploy(
    ctx: &Context,
    recreate: bool,
    no_gitignore: bool,
    no_build: bool,
) -> Result<i32> {
    if no_build && recreate {
        return Err(usage(
            "--no-build releases an existing deployment; --recreate makes a new one",
        ));
    }

    let mut session = ctx.session(None)?;
    // Never start a login from `deploy`: a bad credential is reported, not
    // silently re-authenticated mid-build.
    session.authenticate(&ctx.http, false, false).await?;
    let interactive = std::io::stdin().is_terminal();
    let ask = |q: &str| prompt::confirm(q, false);

    if no_build {
        let mut api = ctx.client(session);
        let address = crate::deploy::release_current(
            &mut api,
            ctx.env.name,
            None,
            interactive,
            wait_seconds(ctx.timeout, ROLLOUT_WAIT_SECONDS)?,
            crate::deploy::POLL_SECONDS,
            &|m| eprintln!("{m}"),
            &ask,
        )
        .await?;
        // The address is the result, and the only thing on stdout.
        println!("{address}");
        ctx.say(&format!("Released. Live at {address}"));
        return Ok(0);
    }

    let mut api = ctx.client(session);
    let address = crate::deploy::deploy(
        &mut api,
        ctx.env.name,
        None,
        recreate,
        !no_gitignore,
        interactive,
        ctx.verbose,
        ctx.quiet,
        wait_seconds(ctx.timeout, BUILD_WAIT_SECONDS)?,
        wait_seconds(ctx.timeout, ROLLOUT_WAIT_SECONDS)?,
        crate::deploy::POLL_SECONDS,
        &ask,
    )
    .await?;

    // The address is the result, and the only thing on stdout. The build log,
    // the progress bar and every status line went to stderr, so
    // `URL=$(freepod deploy)` yields exactly the URL.
    println!("{address}");
    ctx.say(&format!("Deployed. Live at {address}"));
    Ok(0)
}

async fn cmd_delete(ctx: &Context, assume_yes: bool, no_wait: bool) -> Result<i32> {
    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let interactive = std::io::stdin().is_terminal();
    let mut api = ctx.client(session);
    let ask = |q: &str| prompt::confirm(q, false);

    // One echo for progress and for the confirmation preamble alike. `--quiet`
    // silences both.
    crate::delete::delete(
        &mut api,
        ctx.env.name,
        None,
        assume_yes,
        !no_wait,
        interactive,
        wait_seconds(ctx.timeout, ROLLOUT_WAIT_SECONDS)?,
        crate::delete::POLL_SECONDS,
        &|m| ctx.say(m),
        &ask,
    )
    .await?;
    Ok(0)
}

async fn cmd_builds(ctx: &Context, limit: u64, show_all: bool) -> Result<i32> {
    if limit == 0 && !show_all {
        return Err(usage("--limit must be a positive number of builds"));
    }

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let records = crate::history::list_builds(&mut api, user_id).await?;
    let live = crate::history::deployed_image(&mut api, user_id, ctx.env.name, None).await;

    if records.is_empty() {
        ctx.say(&format!(
            "No builds on '{}' yet — `freepod deploy` creates one.",
            ctx.env.name
        ));
        return Ok(0);
    }

    let shown: Vec<Value> = if show_all {
        records.clone()
    } else {
        records.iter().take(limit as usize).cloned().collect()
    };
    println!(
        "{}",
        crate::table::render(&crate::history::rows(
            &shown,
            live.as_deref(),
            ctx.verbose,
            None
        ))
    );

    if live
        .as_ref()
        .is_some_and(|li| shown.iter().any(|r| r.get("image").and_then(|v| v.as_str()) == Some(li.as_str())))
    {
        ctx.say(&format!(
            "{} the build this project's deployment is running.",
            crate::history::LIVE_MARKER
        ));
    }
    if shown.len() < records.len() {
        ctx.say(&format!(
            "Showing {} of {} builds; --all shows every one.",
            shown.len(),
            records.len()
        ));
    }
    Ok(0)
}

async fn cmd_releases(ctx: &Context, limit: u64, show_all: bool) -> Result<i32> {
    if limit == 0 && !show_all {
        return Err(usage("--limit must be a positive number of releases"));
    }

    let project_file = crate::project::require_project(None)?;

    if project_file.env != ctx.env.name && project_file.deployment_id().is_some() {
        return Err(usage(format!(
            "{} records deployment '{}' on '{}', not on '{}'.\n  Re-run without --env \
             (or with --env {}) to list it.",
            project_file.path().display(),
            project_file.deployment_name().unwrap_or(""),
            project_file.env,
            ctx.env.name,
            project_file.env
        )));
    }

    let Some(deployment_id) = project_file.deployment_id() else {
        return Err(usage(format!(
            "{} records no deployment, so there are no releases to list.\n  Run \
             `freepod deploy` to create one.",
            project_file.path().display()
        )));
    };

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let deployment =
        crate::releases::read_deployment(&mut api, user_id, deployment_id).await;
    let records =
        crate::releases::list_releases(&mut api, user_id, deployment_id).await?;

    if records.is_empty() {
        ctx.say(&format!(
            "Deployment '{}' has no releases on '{}'.",
            project_file.deployment_name().unwrap_or(""),
            ctx.env.name
        ));
        return Ok(0);
    }

    let live = crate::releases::applied_number(deployment.as_ref());
    let shown: Vec<Value> = if show_all {
        records.clone()
    } else {
        records.iter().take(limit as usize).cloned().collect()
    };
    println!(
        "{}",
        crate::releases::render_table(&shown, live, ctx.verbose, None)
    );

    if live.is_some_and(|ln| {
        shown
            .iter()
            .any(|r| r.get("number").and_then(|v| v.as_u64()) == Some(ln))
    }) {
        ctx.say(&format!(
            "{} the release this deployment is running.",
            crate::releases::LIVE_MARKER
        ));
    }
    for note in crate::releases::failures(&shown) {
        ctx.say(&note);
    }
    if shown.len() < records.len() {
        ctx.say(&format!(
            "Showing {} of {} releases; --all shows every one.",
            shown.len(),
            records.len()
        ));
    }
    Ok(0)
}

/// The project's recorded deployment, refusing the ways it can be wrong.
fn project_deployment(ctx: &Context) -> Result<crate::project::Project> {
    let project_file = crate::project::require_project(None)?;
    if project_file.env != ctx.env.name && project_file.deployment_id().is_some() {
        return Err(usage(format!(
            "{} records deployment '{}' on '{}', not on '{}'.\n  Re-run without --env \
             (or with --env {}).",
            project_file.path().display(),
            project_file.deployment_name().unwrap_or(""),
            project_file.env,
            ctx.env.name,
            project_file.env
        )));
    }
    if project_file.deployment_id().is_none() {
        return Err(usage(format!(
            "{} records no deployment, so it has no vars.\n  Run `freepod deploy` to \
             create one.",
            project_file.path().display()
        )));
    }
    Ok(project_file)
}

async fn cmd_var_list(ctx: &Context, as_json: bool) -> Result<i32> {
    let project_file = project_deployment(ctx)?;
    let deployment_id = project_file.deployment_id().unwrap().to_string();

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let payload = crate::vars::read(&mut api, user_id, &deployment_id).await?;

    if as_json {
        println!(
            "{}",
            serde_json::to_string_pretty(&payload)
                .map_err(|e| freepod(format!("cannot serialize the vars: {e}")))?
        );
        return Ok(0);
    }
    let table = crate::vars::render_table(&payload);
    if !table.is_empty() {
        println!("{table}");
    } else {
        ctx.say("No vars are set.");
    }
    if payload
        .get("pending")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
        ctx.say(
            "Some vars are not running yet. Apply them with `freepod deploy --no-build`.",
        );
    }
    Ok(0)
}

async fn cmd_var_get(ctx: &Context, key: &str) -> Result<i32> {
    let project_file = project_deployment(ctx)?;
    let deployment_id = project_file.deployment_id().unwrap().to_string();

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let payload = crate::vars::read(&mut api, user_id, &deployment_id).await?;

    let Some(entry) = payload.get("vars").and_then(|v| v.get(key)) else {
        return Err(usage(format!("{key} is not set on this deployment")));
    };
    let Some(value) = entry.get("value") else {
        return Err(usage(format!(
            "{key} is secret, so the platform does not return its value"
        )));
    };
    println!("{}", crate::table::value_str(value));
    Ok(0)
}

async fn cmd_var_set(
    ctx: &Context,
    assignments: &[String],
    secret: bool,
    source: Option<&str>,
    stage: bool,
) -> Result<i32> {
    if assignments.is_empty() && source.is_none() {
        return Err(usage(
            "give KEY=VALUE pairs, a bare KEY to be prompted for, or -f FILE",
        ));
    }

    let mut entries = serde_json::Map::new();
    if let Some(src) = source {
        if let Value::Object(from_file) = crate::vars::load_entries(src)? {
            for (k, v) in from_file {
                entries.insert(k, v);
            }
        }
    }
    if !assignments.is_empty() {
        let interactive = std::io::stdin().is_terminal();
        for (k, v) in crate::vars::parse_assignments(assignments, interactive)? {
            entries.insert(k, serde_json::json!({ "value": v }));
        }
    }

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let project_file = project_deployment(ctx)?;
    let deployment_id = project_file.deployment_id().unwrap().to_string();

    let mut api = ctx.client(session);
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let deployment =
        crate::deploy::read_deployment(&mut api, user_id, &deployment_id).await?;

    let mut entries = Value::Object(entries);
    if secret {
        let declared = crate::vars::mark_sensitive(&mut entries, &deployment);
        if !declared.is_empty() {
            let mut sorted = declared;
            sorted.sort();
            ctx.say(&format!(
                "--secret ignored for {}: this product's schema decides which of its \
                 vars are secret.",
                sorted.join(", ")
            ));
        }
    }
    let count = entries.as_object().map(|o| o.len()).unwrap_or(0);
    let payload =
        crate::vars::write(&mut api, user_id, &deployment_id, &entries).await?;
    finish_var_write(ctx, &mut api, count, &payload, &deployment, stage).await
}

async fn cmd_var_rm(ctx: &Context, keys: &[String], stage: bool) -> Result<i32> {
    let project_file = project_deployment(ctx)?;
    let deployment_id = project_file.deployment_id().unwrap().to_string();

    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let deployment =
        crate::deploy::read_deployment(&mut api, user_id, &deployment_id).await?;
    crate::vars::remove(&mut api, user_id, &deployment_id, keys).await?;
    let payload = crate::vars::read(&mut api, user_id, &deployment_id).await?;
    finish_var_write(ctx, &mut api, keys.len(), &payload, &deployment, stage).await
}

/// Report the write, then roll unless the caller asked to stage it.
///
/// A deployment mid-rollout is refused rather than waited on: the vars are
/// already recorded, so waiting would hold the terminal for a rollout the
/// caller did not ask for.
async fn finish_var_write(
    ctx: &Context,
    api: &mut ApiClient,
    count: usize,
    payload: &Value,
    deployment: &Value,
    stage: bool,
) -> Result<i32> {
    let subject = if count == 1 { "var" } else { "vars" };
    if stage {
        ctx.say(&format!("Recorded {count} {subject}, not applied yet."));
        ctx.say("Apply them with `freepod deploy --no-build`.");
        return Ok(0);
    }
    if !payload
        .get("pending")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
        ctx.say(&format!(
            "Recorded {count} {subject}; nothing changed, so nothing to roll."
        ));
        return Ok(0);
    }

    let status = deployment
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if !crate::deploy::SETTLED_STATUSES.contains(&status) {
        return Err(freepod(format!(
            "deployment '{}' is {}, so it cannot be rolled right now.\n  The {} {} \
             recorded. Apply {} with `freepod deploy --no-build` once the rollout \
             finishes, or pass --stage to skip this step.",
            deployment
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("?"),
            status,
            subject,
            if count == 1 { "is" } else { "are" },
            if count == 1 { "it" } else { "them" }
        )));
    }

    ctx.say(&format!("Recorded {count} {subject}. Rolling the deployment..."));
    let interactive = std::io::stdin().is_terminal();
    let ask = |q: &str| prompt::confirm(q, false);
    let address = match crate::deploy::release_current(
        api,
        ctx.env.name,
        None,
        interactive,
        wait_seconds(ctx.timeout, ROLLOUT_WAIT_SECONDS)?,
        crate::deploy::POLL_SECONDS,
        &|m| ctx.say(m),
        &ask,
    )
    .await
    {
        Ok(address) => address,
        // Same class, so a failed rollout still exits 5 rather than being
        // flattened into the generic failure code by this re-raise.
        Err(e) => {
            return Err(e.with_suffix(
                "  The vars are recorded. Re-run with --stage to skip the rollout, \
                 or apply them later with `freepod deploy --no-build`.",
            ))
        }
    };
    println!("{address}");
    Ok(0)
}

async fn cmd_log(
    ctx: &Context,
    follow: bool,
    tail: Option<u64>,
    release: Option<u64>,
    timestamps: bool,
) -> Result<i32> {
    let mut session = ctx.session(None)?;
    session.authenticate(&ctx.http, false, false).await?;
    let mut api = ctx.client(session);
    let root = std::env::current_dir()
        .map_err(|e| freepod(format!("cannot determine the current directory: {e}")))?;
    let say = |m: &str| ctx.say(m);

    // Interrupting a follow is how a follow ends. Nothing happened to the
    // deployment and nothing should suggest otherwise.
    tokio::select! {
        result = crate::logs::run(
            &mut api,
            ctx.env.name,
            &root,
            follow,
            tail,
            release,
            timestamps,
            &say,
        ) => result,
        _ = tokio::signal::ctrl_c() => {
            ctx.say("");
            Ok(0)
        }
    }
}

/// `a`, `a and b`, `a, b and c` — a list a person reads rather than parses.
fn join_labels(labels: &[&str]) -> String {
    if labels.len() == 1 {
        return labels[0].to_string();
    }
    format!(
        "{} and {}",
        labels[..labels.len() - 1].join(", "),
        labels[labels.len() - 1]
    )
}

async fn cmd_skill_install(
    ctx: &Context,
    names: &[String],
    everything: bool,
    project: bool,
    dest: Option<&std::path::Path>,
) -> Result<i32> {
    if let Some(dest) = dest {
        if !names.is_empty() || everything || project {
            return Err(usage(
                "--dest names the exact path, so it takes no other selector.",
            ));
        }
        let outcome = crate::skill::write(dest, None)?;
        ctx.say(&format!(
            "{}: {}",
            if outcome == "current" {
                "Already current"
            } else {
                "Installed"
            },
            crate::skill::SKILL_NAME
        ));
        println!("{}", dest.display());
        return Ok(0);
    }

    if !names.is_empty() && everything {
        return Err(usage(
            "--agent selects specific agents and --all selects every one.",
        ));
    }

    let chosen = crate::skill::select(names, everything)?;
    if chosen.is_empty() {
        return Err(usage(format!(
            "no supported coding agent found on this machine — none of {} has a \
             configuration directory.\n  Install for one anyway with `--agent NAME`, \
             for all of them with `--all`, or write the file wherever you need it \
             with `--dest PATH`.",
            crate::skill::agent_keys().join(", ")
        )));
    }

    let results = crate::skill::install(&chosen, project)?;

    // The whole report to stderr first, then the paths to stdout, rather than
    // alternating between the two. Both streams reach a terminal by default,
    // and interleaved they read as every line printed twice.
    let width = results
        .iter()
        .map(|(agent, _, _)| agent.label.chars().count())
        .max()
        .unwrap_or(0);
    for (agent, target, outcome) in &results {
        let note = if outcome == "current" {
            " (already current)"
        } else {
            ""
        };
        ctx.say(&format!(
            "  {:<width$}  {}{note}",
            agent.label,
            target.display(),
            width = width
        ));
    }

    let installed: Vec<&str> = results
        .iter()
        .filter(|(_, _, outcome)| outcome != "current")
        .map(|(agent, _, _)| agent.label)
        .collect();
    let scope = if project { "this project" } else { "this machine" };
    if !installed.is_empty() {
        ctx.say(&format!(
            "Installed '{}' for {} on {scope}.",
            crate::skill::SKILL_NAME,
            join_labels(&installed)
        ));
    } else {
        ctx.say(&format!(
            "'{}' was already current for every agent.",
            crate::skill::SKILL_NAME
        ));
    }

    if names.is_empty() && !everything {
        let chosen_labels: Vec<&str> = chosen.iter().map(|a| a.label).collect();
        let missing: Vec<&str> = crate::skill::agents()
            .iter()
            .map(|a| a.label)
            .filter(|label| !chosen_labels.contains(label))
            .collect();
        if !missing.is_empty() {
            ctx.say(&format!(
                "Not detected: {}. Use --agent or --all to install anyway.",
                join_labels(&missing)
            ));
        }
    }

    ctx.say("Agents pick the skill up on their next session.");

    for (_agent, target, _outcome) in &results {
        println!("{}", target.display());
    }
    Ok(0)
}

async fn cmd_skill_show(_ctx: &Context) -> Result<i32> {
    // No trailing newline: the skill is a file, and this is how to read it.
    print!("{}", crate::skill::read_skill());
    Ok(0)
}
