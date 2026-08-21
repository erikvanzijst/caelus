"""The `freepod` command-line entry point.

Stream discipline: results go to stdout, everything else to stderr, so a piped
stdout carries only the result. `deploy` prints one line — the live address —
while the build log, the progress bar, and every status line go to stderr.

Section 11 completes the flag surface (`--quiet`, `NO_COLOR`) and the exit-code
table; what is here is what the commands wired up so far need.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import click

from . import EXIT_ERROR, EXIT_OK, FreepodError, UsageError
from . import delete as delete_module
from . import deploy as deploy_module
from . import history
from . import logs as logs_module
from . import project
from . import skill as skill_module
from . import tos
from .api import ApiClient
from .auth import Session, forget_environment, format_claims, log
from .config import (
    BUILD_WAIT_SECONDS,
    CUSTOM_PRODUCT_SLUG,
    DEFAULT_HTTP_TIMEOUT,
    ENVIRONMENTS,
    ENV_VAR,
    LOGIN_WAIT_SECONDS,
    ROLLOUT_WAIT_SECONDS,
    cache_path_hint,
    environment_names,
    resolve_environment,
    wait_seconds,
)
from .project import PROJECT_FILE, find_project_root, load
from .values import ValueCollector


def _declared_environment() -> Optional[str]:
    """The environment this directory's project declares, or None.

    Best-effort, because it runs for every command, including ones with no
    business in the project: a missing file yields None, and a broken one does
    too — the command that actually needs the project loads it itself and
    reports the real problem.
    """
    root = find_project_root()
    if root is None:
        return None
    try:
        name = load(root).env
    except FreepodError:
        return None
    # A name this client does not know is not a reason to refuse a command that
    # never touches the project — `init --force`, the one way to repair the
    # file, included. The commands that use the pointer report it themselves.
    return name if name in ENVIRONMENTS else None


class Context:
    """What every command needs: which environment, and how loud to be."""

    def __init__(
        self,
        env_name: Optional[str],
        verbose: bool,
        quiet: bool,
        timeout: Optional[int],
    ):
        # An explicit --env outranks the project file; without one, a project
        # in this directory decides where the command goes, so the environment
        # is something the user never has to think about.
        project_env = None if env_name is not None else _declared_environment()
        self.env = resolve_environment(env_name, project_env=project_env)
        self.verbose = verbose
        self.quiet = quiet
        self.timeout = timeout

    def say(self, message: str) -> None:
        """Diagnostics, unless silenced. Never the result."""
        if not self.quiet:
            log(message)

    def session(self, force_flow: Optional[str] = None) -> Session:
        return Session(
            self.env,
            timeout=wait_seconds(self.timeout, LOGIN_WAIT_SECONDS),
            force_flow=force_flow,
            verbose=self.verbose,
        )

    def client(self, session: Session) -> ApiClient:
        return ApiClient(
            self.env,
            session,
            timeout=DEFAULT_HTTP_TIMEOUT,
            verbose=self.verbose,
        )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--env",
    "env_name",
    metavar="NAME",
    help=f"target environment: {environment_names()} (default: the environment "
    f"recorded in {PROJECT_FILE}, else {ENV_VAR}, else prod)",
)
@click.option("--verbose", is_flag=True, help="show extra detail, including token claims")
@click.option(
    "--quiet",
    is_flag=True,
    help="suppress progress and diagnostics; results and errors still appear",
)
@click.option(
    "--timeout",
    type=int,
    metavar="SECONDS",
    help="override the wait for whichever operation is in progress — it means "
    f"something different per command (login {LOGIN_WAIT_SECONDS}s, build "
    f"{BUILD_WAIT_SECONDS}s, rollout {ROLLOUT_WAIT_SECONDS}s by default)",
)
@click.version_option(package_name="freepod")
@click.pass_context
def cli(
    ctx: click.Context,
    env_name: Optional[str],
    verbose: bool,
    quiet: bool,
    timeout: Optional[int],
) -> None:
    """Take a local project directory to a running Freepod deployment."""
    if verbose and quiet:
        raise UsageError("--verbose and --quiet contradict each other; pick one")

    # An unset shell variable expands to this. Falling through to the default
    # would deploy to prod on the strength of a variable the script believed it
    # had set, which is the one outcome an explicit --env must never produce.
    if env_name is not None and not env_name.strip():
        raise UsageError(
            f"--env was given an empty value — name one of {environment_names()}, "
            f"or omit it to use the environment recorded in {PROJECT_FILE}"
        )

    # Left as None, click decides per-stream, which would still color a
    # terminal when `NO_COLOR` asks it not to. False forces the escape codes
    # stripped everywhere.
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        ctx.color = False

    ctx.obj = Context(env_name, verbose, quiet, timeout)


@cli.command()
@click.option("--loopback", "flow", flag_value="loopback", help="force the browser flow")
@click.option("--device", "flow", flag_value="device", help="force the device flow")
@click.option("--force", is_flag=True, help="ignore any cached credential and re-authenticate")
@click.pass_obj
def login(context: Context, flow: Optional[str], force: bool) -> None:
    """Authenticate against Freepod and cache the credential."""
    session = context.session(force_flow=flow)
    session.authenticate(force_login=force)

    with context.client(session) as api:
        me = api.me()

        context.say(
            f"Authenticated as {me.get('email')} (user id {me.get('id')}) on "
            f"'{context.env.name}'."
        )
        context.say(f"  flow       : {session.flow_used or 'none — reused a cached credential'}")
        context.say(f"  credential : {session.credential_source}")
        if context.verbose and session.access_token:
            context.say(format_claims(session.access_token))

        # Offered, never required. `login` is also how a headless box and a CI
        # job get a credential, and how someone who only wants `whoami` gets
        # one; refusing to finish over an unaccepted agreement would break all
        # three for a fact only `deploy` actually needs. A decline is recorded
        # nowhere and simply leaves `deploy` to ask again.
        status = tos.settle(api, interactive=sys.stdin.isatty())
        if status == tos.VERSION_UNKNOWN:
            context.say(f"  terms      : not accepted — accept them at {context.env.api_base}.")
        elif status != tos.ACCEPTED:
            context.say(
                "  terms      : not accepted — `freepod deploy` will ask before "
                "creating your first deployment."
            )


@cli.command()
@click.pass_obj
def logout(context: Context) -> None:
    """Discard the cached credential for the selected environment."""
    name = context.env.name
    if forget_environment(name):
        context.say(f"Discarded the cached credential for '{name}' from {cache_path_hint()}.")
    else:
        context.say(f"No cached credential for '{name}' in {cache_path_hint()}.")
    context.say(
        "Note: this only forgets the local copy. The credential remains valid on "
        "the platform until it is revoked there — use the Keycloak account console "
        "(Applications -> offline sessions)."
    )


@cli.command()
@click.pass_obj
def whoami(context: Context) -> None:
    """Report who the cached credential authenticates as."""
    session = context.session()
    # Never start a login from `whoami`: a command that merely reports identity
    # should say "not authenticated" rather than opening a browser.
    session.authenticate(interactive=False)

    with context.client(session) as api:
        me = api.me()

    click.echo(f"{me.get('email')}")
    click.echo(f"user id: {me.get('id')}")
    if me.get("is_admin"):
        click.echo("admin:   yes")
    context.say(f"Environment '{context.env.name}' ({context.env.api_base}).")
    if context.verbose and session.access_token:
        context.say(format_claims(session.access_token))


@cli.command()
@click.option(
    "--force",
    is_flag=True,
    help=f"overwrite an existing {PROJECT_FILE}, discarding its deployment pointer",
)
@click.pass_obj
def init(context: Context, force: bool) -> None:
    """Set up the current directory as a Freepod project.

    Reads only. No deployment is created — that is `freepod deploy`'s job, so
    that a failure writing the project file cannot leave behind a provisioned
    resource the user cannot see.
    """
    root = Path.cwd()
    target = root / PROJECT_FILE

    if target.exists() and not force:
        raise UsageError(
            f"{target} already exists. Re-run with --force to discard it and start "
            f"over — note that this also discards the deployment pointer, so the "
            f"existing deployment would be orphaned.\n"
            f"  To change a value, edit {PROJECT_FILE} directly; `freepod deploy` "
            f"asks for anything required that is missing."
        )
    if target.exists() and force:
        existing = project.load(root)
        if existing.deployment_name:
            context.say(
                f"Warning: --force discards the pointer to deployment "
                f"'{existing.deployment_name}'. It will keep running, and this "
                f"project will no longer be able to update it."
            )

    session = context.session()
    session.authenticate(interactive=False)

    with context.client(session) as api:
        # `/api/me` first: everything else init reads is public and would be
        # answered anonymously however bad the credential is. See design D15.
        api.me()

        product = api.find_product(CUSTOM_PRODUCT_SLUG)
        if product is None:
            raise FreepodError(
                f"this instance does not offer user-supplied application deployments "
                f"({context.env.api_base} publishes no '{CUSTOM_PRODUCT_SLUG}' product)."
            )

        template = product.get("template") or {}
        schema = template.get("values_schema_json") or {}
        if not schema.get("properties"):
            raise FreepodError(
                f"the '{CUSTOM_PRODUCT_SLUG}' product's template declares no user "
                f"values schema, so there is nothing to configure — this is a "
                f"platform problem, please report it."
            )

        context.say(f"Product '{product.get('name')}' (template {template.get('id')}).")

        collector = ValueCollector(
            schema,
            domains=api.domains(),
            check_hostname=api.check_hostname,
        )
        values = collector.collect()

    new = project.Project(root=root, env=context.env.name, user_values=values)
    new.save()

    # The path is the result; everything else is commentary.
    click.echo(str(target))
    context.say(
        f"Initialized for '{context.env.name}'. Run `freepod deploy` to build and release."
    )


@cli.command()
@click.option(
    "--recreate",
    is_flag=True,
    help="discard the recorded deployment pointer and create a new deployment",
)
@click.option(
    "--no-gitignore",
    "no_gitignore",
    is_flag=True,
    help="pack the tree without applying .gitignore rules",
)
@click.pass_obj
def deploy(context: Context, recreate: bool, no_gitignore: bool) -> None:
    """Build the current project and release it to its deployment.

    Preflight, pack, upload, build, release — in that order, so that everything
    a cheap read can refuse is refused before a build is spent.

    `--no-gitignore` is an `is_flag` option negated here rather than a
    `flag_value=False` one, because click stopped honoring a `True` default
    alongside a `False` flag value in 8.3 and silently inverted it — which is
    the kind of default that fails by packing more than the user asked for.
    `tests/test_cli.py` pins it.
    """
    session = context.session()
    session.authenticate(interactive=False)

    with context.client(session) as api:
        address = deploy_module.deploy(
            api,
            context.env.name,
            recreate=recreate,
            honor_gitignore=not no_gitignore,
            verbose=context.verbose,
            quiet=context.quiet,
            interactive=sys.stdin.isatty(),
            build_timeout=wait_seconds(context.timeout, BUILD_WAIT_SECONDS),
            rollout_timeout=wait_seconds(context.timeout, ROLLOUT_WAIT_SECONDS),
        )

    # The address is the result, and the only thing on stdout. The build log,
    # the progress bar and every status line went to stderr, so
    # `URL=$(freepod deploy)` yields exactly the URL.
    click.echo(address)
    context.say(f"Deployed. Live at {address}")


@cli.command()
@click.option(
    "--yes",
    "-y",
    "assume_yes",
    is_flag=True,
    help="skip the confirmation prompt — the only way to delete unattended",
)
@click.option(
    "--no-wait",
    "no_wait",
    is_flag=True,
    help="return once the teardown is scheduled instead of following it",
)
@click.pass_obj
def delete(context: Context, assume_yes: bool, no_wait: bool) -> None:
    """Delete this project's deployment and everything it stores.

    The teardown is followed to completion by default: the hostname stays
    claimed until it lands, so a `delete` that returned early would collide
    with itself on the next `freepod deploy`.

    Nothing is written to stdout — a deletion has no result to pipe.
    """
    session = context.session()
    session.authenticate(interactive=False)

    with context.client(session) as api:
        delete_module.delete(
            api,
            context.env.name,
            assume_yes=assume_yes,
            wait=not no_wait,
            interactive=sys.stdin.isatty(),
            timeout=wait_seconds(context.timeout, ROLLOUT_WAIT_SECONDS),
            # One echo for progress and for the confirmation preamble alike.
            # `--quiet` silences both, which is why the question itself names
            # the deployment rather than relying on the lines above it.
            echo=context.say,
        )


@cli.command()
@click.option(
    "--limit",
    type=int,
    metavar="N",
    default=history.DEFAULT_LIMIT,
    help=f"how many builds to show (default: {history.DEFAULT_LIMIT})",
)
@click.option("--all", "show_all", is_flag=True, help="show every build, ignoring --limit")
@click.pass_obj
def builds(context: Context, limit: int, show_all: bool) -> None:
    """List this account's builds, most recent first.

    Builds belong to the account rather than to a project — the platform has no
    notion of one — so every build made from this account is listed, whichever
    directory produced it. The build the current project's deployment is
    running is marked.

    The table is the result and goes to stdout; `--verbose` prints image
    references in full rather than abbreviating their digests.
    """
    if limit <= 0 and not show_all:
        raise UsageError("--limit must be a positive number of builds")

    session = context.session()
    session.authenticate(interactive=False)

    with context.client(session) as api:
        user_id = api.me()["id"]
        records = history.list_builds(api)
        live = history.deployed_image(api, user_id, context.env.name)

    if not records:
        context.say(
            f"No builds on '{context.env.name}' yet — `freepod deploy` creates one."
        )
        return

    shown = records if show_all else records[:limit]
    click.echo(
        history.render(
            history.rows(shown, live_image=live, full_image=context.verbose)
        )
    )

    if live and any(record.get("image") == live for record in shown):
        context.say(
            f"{history.LIVE_MARKER} the build this project's deployment is running."
        )
    if len(shown) < len(records):
        context.say(
            f"Showing {len(shown)} of {len(records)} builds; --all shows every one."
        )


def _join(labels: list) -> str:
    """`a`, `a and b`, `a, b and c` — a list a person reads rather than parses."""
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


@cli.group()
def skill() -> None:
    """Install the deployment instructions for your coding agents.

    The client ships a skill file describing this platform's contract — bind
    `$PORT`, no disk, no environment variables, S3 for state — which is what a
    coding agent needs before it can deploy anything here successfully. It is
    packaged with the client so the two versions cannot drift apart.

    `SKILL.md` is a format every supported agent reads, so one file serves all
    of them and only the destination differs.
    """


@skill.command("install")
@click.option(
    "--agent",
    "names",
    metavar="NAME",
    multiple=True,
    help="install for this agent whether or not it is detected; repeatable",
)
@click.option("--all", "everything", is_flag=True, help="install for every supported agent")
@click.option(
    "--project",
    is_flag=True,
    help="install into this directory's per-agent skill folders rather than the home directory",
)
@click.option(
    "--dest",
    type=click.Path(path_type=Path),
    help=f"write {skill_module.SKILL_FILE} to this exact path instead, for an agent not listed",
)
@click.pass_obj
def skill_install(
    context: Context,
    names: tuple,
    everything: bool,
    project: bool,
    dest: Optional[Path],
) -> None:
    """Write the packaged skill where a coding agent will find it.

    With no options it installs for every supported agent it can see on this
    machine, which it decides by looking for each one's configuration
    directory. `--agent` and `--all` override that; `--dest` bypasses the
    table entirely.

    Existing copies are replaced without asking. The file is generated, the
    path belongs to this client, and a newer client's skill has to be able to
    supersede an older one for `pip install --upgrade` to mean anything.

    The installed paths are the result and go to stdout, one per line; which
    agent each belongs to goes to stderr like every other diagnostic.
    """
    if dest is not None:
        if names or everything or project:
            raise UsageError("--dest names the exact path, so it takes no other selector.")
        outcome = skill_module.write(dest)
        context.say(
            f"{'Already current' if outcome == 'current' else 'Installed'}: "
            f"{skill_module.SKILL_NAME}"
        )
        click.echo(str(dest))
        return

    if names and everything:
        raise UsageError("--agent selects specific agents and --all selects every one.")

    chosen = skill_module.select(names, everything)
    if not chosen:
        raise UsageError(
            "no supported coding agent found on this machine — none of "
            f"{', '.join(skill_module.agent_keys())} has a configuration directory.\n"
            "  Install for one anyway with `--agent NAME`, for all of them with "
            "`--all`, or write the file wherever you need it with `--dest PATH`."
        )

    results = skill_module.install(chosen, project=project)

    # The whole report to stderr first, then the paths to stdout, rather than
    # alternating between the two. Both streams reach a terminal by default,
    # and interleaved they read as every line printed twice.
    width = max(len(agent.label) for agent, _, _ in results)
    for agent, target, outcome in results:
        note = " (already current)" if outcome == "current" else ""
        context.say(f"  {agent.label.ljust(width)}  {target}{note}")

    installed = [agent.label for agent, _, outcome in results if outcome != "current"]
    scope = "this project" if project else "this machine"
    if installed:
        context.say(f"Installed '{skill_module.SKILL_NAME}' for {_join(installed)} on {scope}.")
    else:
        context.say(f"'{skill_module.SKILL_NAME}' was already current for every agent.")

    if not names and not everything:
        missing = [
            agent.label for agent in skill_module.agents() if agent not in set(chosen)
        ]
        if missing:
            context.say(
                f"Not detected: {_join(missing)}. Use --agent or --all to install anyway."
            )

    context.say("Agents pick the skill up on their next session.")

    for _agent, target, _outcome in results:
        click.echo(str(target))


@skill.command("show")
def skill_show() -> None:
    """Print the packaged skill to stdout.

    For any agent runtime that is not Claude Code, or to read what `install`
    would write before it writes it.
    """
    click.echo(skill_module.read_skill(), nl=False)


def main(argv: Optional[list] = None) -> int:
    """Run the CLI and map every failure onto its exit code.

    Section 11 completes the exit-code table; the rows reachable from the
    commands wired up so far are handled here.
    """
    try:
        cli.main(args=argv, standalone_mode=False)
        return EXIT_OK
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except click.ClickException as exc:
        exc.show()
        return int(exc.exit_code)
    except click.Abort:
        log("\nInterrupted.")
        return 130
    except UsageError as exc:
        log(f"error: {exc}")
        return exc.exit_code
    except FreepodError as exc:
        log(f"\nerror: {exc}")
        return exc.exit_code
    except KeyboardInterrupt:
        log("\nInterrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001 - the "unexpected error" row
        log(f"\nunexpected error: {exc.__class__.__name__}: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


@cli.command(name="log")
@click.option("-f", "--follow", is_flag=True, help="keep the stream open and print lines as they arrive")
@click.option(
    "-n", "--tail", type=int, metavar="LINES",
    help="how many trailing lines to start with (default: the platform's)",
)
@click.option(
    "-r", "--release", type=int, metavar="NUMBER",
    help="pin to one release by its number, including one that failed and was rolled back",
)
@click.option(
    "-t", "--timestamps", is_flag=True,
    help="prefix each line with the time the platform recorded for it",
)
@click.pass_obj
def log_command(
    context: Context,
    follow: bool,
    tail: Optional[int],
    release: Optional[int],
    timestamps: bool,
) -> None:
    """Stream this project's application output.

    Log lines go to stdout and everything this client says goes to stderr, so
    `freepod log > app.log` captures the application and nothing else. That is
    the opposite split from `deploy`, where the build log is the platform
    narrating and the address is the result.

    With `-f` the stream stays open across a redeploy, because you are watching
    an application rather than a container.
    """
    session = context.session()
    session.authenticate(interactive=False)
    with context.client(session) as api:
        try:
            code = logs_module.run(
                api,
                context.env.name,
                root=Path.cwd(),
                follow=follow,
                tail=tail,
                release=release,
                timestamps=timestamps,
                say=context.say,
            )
        except KeyboardInterrupt:
            # Interrupting a follow is how a follow ends. Nothing happened to
            # the deployment and nothing should suggest otherwise.
            context.say("")
            raise SystemExit(EXIT_OK)
    raise SystemExit(code)
