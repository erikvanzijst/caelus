//! `freepod log` — reading a deployment's application output.
//!
//! Mirrors `logs.py`. Stream discipline is the opposite of `deploy`'s, and
//! deliberately so. There, the build log is the platform narrating its
//! progress towards a result, so it goes to stderr and leaves stdout for the
//! address. Here the log lines **are** the result: the user asked for them,
//! and they must survive `freepod log > app.log` and a pipe into `grep`. So
//! lines go to stdout and every word the client says about itself goes to
//! stderr.
//!
//! The transport is Server-Sent Events over the existing `ApiClient`, parsed
//! line by line. SSE is a line format rather than a protocol needing a
//! library.

use std::collections::HashSet;
use std::io::Write;
use std::path::Path;
use std::time::Duration;

use futures_util::StreamExt;
use serde_json::Value;

use crate::api::{ApiClient, StreamOutcome};
use crate::config::{
    LOG_RECONNECT_ATTEMPTS, LOG_RECONNECT_BACKOFF_SECONDS, LOG_STREAM_READ_TIMEOUT,
};
use crate::errors::{freepod, usage, Error, Result};
use crate::project::{find_project_root, load};
use crate::table::value_str;

/// Event names the platform emits. A line beginning with ':' is a comment —
/// the keepalive — and is discarded without ever reaching the output.
const EVENT_LOG: &str = "log";
const EVENT_ERROR: &str = "error";
const EVENT_END: &str = "end";

/// Clean endings. `lifetime` is resumable: the platform caps how long one
/// authorization may keep serving, and a follow reconnects straight through
/// it.
const END_LIFETIME: &str = "lifetime";
const END_COMPLETE: &str = "complete";

/// One parsed SSE event.
struct Event {
    event: String,
    data: Value,
}

/// What the client must remember across a reconnect.
///
/// Only the timestamp of the last event received — the same field
/// `--timestamps` renders. Tracking a separate resume value would mean two
/// representations of one fact, which is how what is displayed and what is
/// resumed from come to disagree.
#[derive(Default)]
pub struct Cursor {
    ts: Option<String>,
    lines: usize,
    /// Every release seen so far, so a rollover is announced once per release
    /// rather than prefixed onto every line. A *set*, not the last value seen:
    /// during a rollout the old and new pods write concurrently and the
    /// platform returns both interleaved. Survives a reconnect, so a resume
    /// does not re-announce what it was already following.
    seen_releases: HashSet<String>,
}

impl Cursor {
    pub fn lines(&self) -> usize {
        self.lines
    }
}

/// Why a stream stopped. A transport-level interruption is retryable; a
/// semantic error is not — the platform said something, and repeating the
/// request would just hear it again.
enum StreamFailure {
    Interrupted(String),
    Fatal(Error),
}

// --------------------------------------------------------------------------
// Resolving what to read
// --------------------------------------------------------------------------

/// The deployment this project points at, for this environment.
///
/// Says so plainly when there is nothing to read rather than guessing from
/// the account's other deployments: a wrong guess prints another
/// application's output under this project's name, which is worse than an
/// error.
pub fn resolve_deployment(root: &Path, env_name: &str) -> Result<String> {
    let found = find_project_root(Some(root)).ok_or_else(|| {
        freepod(
            "no Freepod project here — `freepod log` reads the deployment recorded in \
             `.freepod-rust.json`.\n  Run it from a project directory, or run `freepod \
             init` to create one.",
        )
    })?;
    let project = load(&found)?;
    if project.env != env_name && project.deployment_id().is_some() {
        // The recorded deployment is minted on another environment. Naming it
        // keeps the pointer legible: a bare "no deployment here" would send
        // the user to `freepod deploy` for a project that already has one.
        return Err(usage(format!(
            "this project's deployment is on '{}', not on '{}'.\n  Re-run without \
             --env (or with --env {}) to read it.",
            project.env, env_name, project.env
        )));
    }
    let Some(deployment_id) = project.deployment_id() else {
        return Err(freepod(format!(
            "this project has no deployment on '{env_name}' yet — there is nothing \
             to read.\n  Run `freepod deploy` first."
        )));
    };
    Ok(deployment_id.to_string())
}

// --------------------------------------------------------------------------
// SSE
// --------------------------------------------------------------------------

/// Turns a line stream into events, discarding keepalives.
///
/// Keepalives leave no trace at all — not a blank line, not an empty event —
/// so a quiet period is invisible in redirected output.
struct SseParser {
    event_name: String,
    data_parts: Vec<String>,
}

impl SseParser {
    fn new() -> Self {
        Self {
            event_name: "message".to_string(),
            data_parts: Vec::new(),
        }
    }

    /// Feed one line. A blank line dispatches the pending event, if any.
    ///
    /// The caller may or may not have removed the line terminator; both
    /// `\n` and a preceding `\r` are stripped here, as `iter_lines()` does
    /// on the Python side.
    fn feed(&mut self, raw: &str) -> Result<Option<Event>> {
        let stripped = raw.strip_suffix('\n').unwrap_or(raw);
        let line = stripped.strip_suffix('\r').unwrap_or(stripped);
        if line.starts_with(':') {
            // A comment. The platform's keepalive, describing the connection
            // rather than the log; it carries no id and moves no cursor.
            return Ok(None);
        }
        if line.is_empty() {
            if !self.data_parts.is_empty() {
                let payload = self.data_parts.join("\n");
                self.data_parts.clear();
                let name = std::mem::replace(&mut self.event_name, "message".to_string());
                let data: Value = serde_json::from_str(&payload).map_err(|_| {
                    freepod(format!(
                        "the platform sent a log event this client cannot parse: {}",
                        payload.chars().take(200).collect::<String>()
                    ))
                })?;
                return Ok(Some(Event { event: name, data }));
            }
            self.event_name = "message".to_string();
            return Ok(None);
        }
        let (field, value) = match line.find(':') {
            Some(idx) => (&line[..idx], &line[idx + 1..]),
            None => (line, ""),
        };
        let value = value.strip_prefix(' ').unwrap_or(value);
        if field == "event" {
            self.event_name = value.to_string();
        } else if field == "data" {
            self.data_parts.push(value.to_string());
        }
        // `id` is ignored on purpose: it mirrors the timestamp the event
        // already carries, and tracking two representations of one fact is
        // how they drift apart.
        Ok(None)
    }
}

// --------------------------------------------------------------------------
// Rendering
// --------------------------------------------------------------------------

/// Render one log event.
///
/// The optional timestamp prefix appears before the line, so output stays
/// splittable by position. Timestamps are off by default because many
/// applications already stamp their own output.
pub fn format_line(data: &Value, timestamps: bool) -> String {
    let line = data.get("line").and_then(|v| v.as_str()).unwrap_or("");
    if timestamps {
        let ts = format_timestamp(data.get("ts").unwrap_or(&Value::Null));
        format!("{ts} {line}")
    } else {
        line.to_string()
    }
}

/// Render a nanosecond timestamp as UTC, without ever touching a float.
///
/// `parse`, never `float`: the value is ~1.76e18 against a f64's
/// exact-integer ceiling of ~9.01e15, so any float round trip silently
/// corrupts both the rendered time and the resume point.
pub fn format_timestamp(ts: &Value) -> String {
    let Some(text) = ts.as_str() else {
        return "-".to_string();
    };
    if text.is_empty() {
        return "-".to_string();
    }
    let Ok(nanos) = text.parse::<i64>() else {
        return "-".to_string();
    };
    let seconds = nanos / 1_000_000_000;
    let remainder = (nanos % 1_000_000_000).unsigned_abs();
    let Some(stamp) = chrono::DateTime::from_timestamp(seconds, 0) else {
        return "-".to_string();
    };
    format!(
        "{}.{remainder:09}Z",
        stamp.format("%Y-%m-%dT%H:%M:%S")
    )
}

// --------------------------------------------------------------------------
// Streaming
// --------------------------------------------------------------------------

/// Consume one connection. Returns the platform's end reason, or Ok(None) if
/// it stopped without one.
///
/// An Ok(None) return is an *interruption*, not an ending: the platform says
/// why it finished when it finishes on purpose.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
async fn stream_once(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    cursor: &mut Cursor,
    follow: bool,
    tail: Option<u64>,
    release: Option<u64>,
    timestamps: bool,
    out: &mut dyn Write,
    say: &dyn Fn(&str),
) -> std::result::Result<Option<String>, StreamFailure> {
    let mut params: Vec<(String, String)> = Vec::new();
    if follow {
        params.push(("follow".to_string(), "true".to_string()));
    }
    if let Some(t) = tail {
        params.push(("tail".to_string(), t.to_string()));
    }
    if let Some(r) = release {
        params.push(("release".to_string(), r.to_string()));
    }
    if let Some(ts) = &cursor.ts {
        // Inclusive, and the platform's business: a line sharing this instant
        // may arrive twice, which is the mechanism working. Suppressing
        // duplicates here would risk discarding a line that was genuinely new.
        params.push(("since".to_string(), ts.clone()));
    }

    let path = format!("/api/users/{user_id}/deployments/{deployment_id}/log");
    let outcome = api
        .stream_request(&path, Some(&params))
        .await
        .map_err(StreamFailure::Fatal)?;
    let response = match outcome {
        StreamOutcome::Live(response) => response,
        StreamOutcome::Refused { status, detail } => {
            return match status {
                503 => Err(StreamFailure::Fatal(freepod(format!(
                    "the platform cannot reach its log store, so it cannot say what this \
                     application printed. This is a platform condition, not a silent \
                     application.\n  {detail}"
                )))),
                404 => Err(StreamFailure::Fatal(freepod(format!(
                    "no such deployment or release on '{}'.\n  {detail}",
                    api.env.name
                )))),
                _ => Err(StreamFailure::Fatal(freepod(format!(
                    "could not read the log: HTTP {status} {detail}"
                )))),
            };
        }
    };

    let mut stream = response.bytes_stream();
    let mut buf: Vec<u8> = Vec::new();
    let mut parser = SseParser::new();
    // A followed stream must not carry the client's ordinary request timeout,
    // which would disconnect any application quiet for longer than an ordinary
    // request should take. What bounds a follow is the platform's silence, not
    // the application's.
    let read_timeout =
        follow.then(|| Duration::from_secs(LOG_STREAM_READ_TIMEOUT));

    loop {
        let chunk = match read_timeout {
            Some(t) => match tokio::time::timeout(t, stream.next()).await {
                Ok(chunk) => chunk,
                Err(_) => {
                    return Err(StreamFailure::Interrupted(format!(
                        "the platform was silent for {LOG_STREAM_READ_TIMEOUT}s"
                    )))
                }
            },
            None => stream.next().await,
        };
        let Some(chunk) = chunk else {
            break;
        };
        let chunk =
            chunk.map_err(|e| StreamFailure::Interrupted(format!("could not read the stream: {e}")))?;
        buf.extend_from_slice(&chunk);

        while let Some(pos) = buf.iter().position(|&b| b == b'\n') {
            let line_bytes: Vec<u8> = buf.drain(..=pos).collect();
            let line = String::from_utf8_lossy(&line_bytes);
            match parser.feed(&line) {
                Ok(Some(event)) => {
                    let result = handle_event(
                        &event,
                        cursor,
                        timestamps,
                        out,
                        say,
                    );
                    if let Some(r) = result {
                        return r;
                    }
                }
                Ok(None) => {}
                Err(e) => return Err(StreamFailure::Fatal(e)),
            }
        }
    }
    Ok(None)
}

/// Apply one event to the cursor and the output. Returns Some(...) where the
/// stream is over: the end reason, or a fatal error.
fn handle_event(
    event: &Event,
    cursor: &mut Cursor,
    timestamps: bool,
    out: &mut dyn Write,
    say: &dyn Fn(&str),
) -> Option<std::result::Result<Option<String>, StreamFailure>> {
    match event.event.as_str() {
        EVENT_LOG => {
            if let Some(release_id) = event.data.get("release") {
                let rid = value_str(release_id);
                if !rid.is_empty() && rid != "-" && !cursor.seen_releases.contains(&rid) {
                    // A rollover: the user is watching an application, not a
                    // container, so a redeploy shows up here rather than ending
                    // the stream. On stderr — it is the client describing what
                    // it is doing, not the application's output. The first
                    // release seen is what the stream opened on and is not a
                    // rollover.
                    if !cursor.seen_releases.is_empty() {
                        say(&format!("Now following release {rid}."));
                    }
                    cursor.seen_releases.insert(rid);
                }
            }
            let formatted = format_line(&event.data, timestamps);
            if writeln!(out, "{formatted}").is_err() || out.flush().is_err() {
                return Some(Err(StreamFailure::Interrupted(
                    "could not write the log output".to_string(),
                )));
            }
            if let Some(ts) = event.data.get("ts") {
                let ts = value_str(ts);
                if !ts.is_empty() && ts != "-" {
                    cursor.ts = Some(ts);
                }
            }
            cursor.lines += 1;
            None
        }
        EVENT_ERROR => {
            // Mid-stream, so the status code is long gone — which is the
            // reason the platform frames this rather than just closing.
            let message = event
                .data
                .get("message")
                .and_then(|v| v.as_str())
                .map(String::from)
                .or_else(|| {
                    event
                        .data
                        .get("error")
                        .and_then(|v| v.as_str())
                        .map(String::from)
                })
                .unwrap_or_default();
            Some(Err(StreamFailure::Fatal(freepod(format!(
                "the platform interrupted the stream: {message}"
            )))))
        }
        EVENT_END => Some(Ok(Some(
            event
                .data
                .get("reason")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        ))),
        _ => None,
    }
}

/// Follow a deployment, reconnecting from the cursor rather than the present.
///
/// Restarting at the present would silently lose everything written during
/// the outage — which is when the interesting output tends to happen.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
pub async fn follow_stream(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    tail: Option<u64>,
    release: Option<u64>,
    timestamps: bool,
    out: &mut dyn Write,
    say: &dyn Fn(&str),
) -> Result<Cursor> {
    let mut cursor = Cursor::default();
    let mut failures: u32 = 0;
    let mut first = true;

    loop {
        let delivered = cursor.lines;
        // The tail is a *first connect* concern. Re-requesting it on a
        // reconnect would reprint what the user has already read.
        let result = stream_once(
            api,
            user_id,
            deployment_id,
            &mut cursor,
            true,
            if first { tail } else { None },
            release,
            timestamps,
            out,
            say,
        )
        .await;
        first = false;

        match result {
            Ok(Some(reason)) => {
                // Progress resets the budget. A long follow that drops every
                // few hours and resumes cleanly each time is working, not
                // failing, and counting those cumulatively would eventually
                // abandon a healthy stream.
                if cursor.lines > delivered {
                    failures = 0;
                }
                if reason == END_LIFETIME {
                    // The platform caps how long one authorization keeps
                    // serving. Expected and resumable, so reconnect straight
                    // through it without saying anything: the user asked to
                    // watch an application, not a connection.
                    continue;
                }
                if reason == END_COMPLETE {
                    // The platform said it had finished — a release that never
                    // ran, or a finite read. That is an answer, not an
                    // interruption.
                    return Ok(cursor);
                }
                // Any other end reason is an answer too.
                return Ok(cursor);
            }
            Ok(None) => {
                // No end event: the response ended without the platform saying
                // it was done, so something between here and there dropped it.
                // In follow mode that is an interruption to resume from, not
                // the end of the log.
                failures += 1;
                if failures > LOG_RECONNECT_ATTEMPTS {
                    return Err(freepod(format!(
                        "the log stream was interrupted and could not be re-established \
                         after {LOG_RECONNECT_ATTEMPTS} attempts (the stream kept ending \
                         without the platform saying it had finished).\n  This says nothing \
                         about the application, which may still be running — try again, or \
                         check `freepod status`."
                    )));
                }
                let delay =
                    LOG_RECONNECT_BACKOFF_SECONDS * 2f64.powi((failures - 1) as i32);
                say(&format!(
                    "Stream ended unexpectedly; reconnecting in {:.0}s...",
                    delay
                ));
                tokio::time::sleep(Duration::from_secs_f64(delay)).await;
            }
            Err(StreamFailure::Fatal(e)) => return Err(e),
            Err(StreamFailure::Interrupted(message)) => {
                failures += 1;
                if failures > LOG_RECONNECT_ATTEMPTS {
                    return Err(freepod(format!(
                        "the log stream was interrupted and could not be re-established \
                         after {LOG_RECONNECT_ATTEMPTS} attempts ({message}).\n  This says \
                         nothing about the application, which may still be running — try \
                         again, or check `freepod status`."
                    )));
                }
                let delay =
                    LOG_RECONNECT_BACKOFF_SECONDS * 2f64.powi((failures - 1) as i32);
                // Never silent: a gap in a followed stream that nobody
                // mentioned reads as the application having gone quiet.
                say(&format!(
                    "Stream interrupted ({message}); reconnecting in {:.0}s...",
                    delay
                ));
                tokio::time::sleep(Duration::from_secs_f64(delay)).await;
            }
        }
    }
}

// --------------------------------------------------------------------------
// The command
// --------------------------------------------------------------------------

/// Stream the project's deployment log. Returns an exit code.
#[allow(clippy::too_many_arguments)] // mirrors the reference signature
pub async fn run(
    api: &mut ApiClient,
    env_name: &str,
    root: &Path,
    follow: bool,
    tail: Option<u64>,
    release: Option<u64>,
    timestamps: bool,
    say: &dyn Fn(&str),
) -> Result<i32> {
    let deployment_id = resolve_deployment(root, env_name)?;
    let user_id = api
        .me()
        .await?
        .get("id")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    if let Some(r) = release {
        say(&format!("Reading release {r} of deployment {deployment_id}."));
    }

    let mut out = std::io::stdout();
    let cursor = if follow {
        follow_stream(
            api,
            user_id,
            &deployment_id,
            tail,
            release,
            timestamps,
            &mut out,
            say,
        )
        .await?
    } else {
        let mut cursor = Cursor::default();
        match stream_once(
            api,
            user_id,
            &deployment_id,
            &mut cursor,
            false,
            tail,
            release,
            timestamps,
            &mut out,
            say,
        )
        .await
        {
            Ok(_) => cursor,
            Err(StreamFailure::Fatal(e)) => return Err(e),
            Err(StreamFailure::Interrupted(message)) => return Err(freepod(message)),
        }
    };

    if cursor.lines() == 0 {
        // An empty result is an answer, and saying so is what keeps it
        // legible as one rather than as a broken command. On stderr, so a
        // redirected stdout stays byte-for-byte the application's own output
        // — which here is correctly empty.
        say("The application has produced no output.");
    }
    Ok(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn parse(lines: &[&str]) -> Result<Vec<Event>> {
        let mut parser = SseParser::new();
        let mut events = Vec::new();
        for line in lines {
            if let Some(event) = parser.feed(line)? {
                events.push(event);
            }
        }
        Ok(events)
    }

    #[test]
    fn parse_dispatches_on_the_blank_line() {
        let events = parse(&[
            "event: log",
            "data: {\"line\": \"hello\", \"ts\": \"1\"}",
            "",
        ])
        .unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].event, "log");
        assert_eq!(events[0].data["line"], json!("hello"));
    }

    #[test]
    fn parse_strips_line_terminators() {
        // The chunk loop hands lines over with their trailing newline still
        // on; the blank dispatch line is then "\n", not "".
        let events = parse(&[
            "id: 1787876273422054370\n",
            "event: log\n",
            "data: {\"line\": \"hello\", \"ts\": \"1\"}\n",
            "\n",
        ])
        .unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].event, "log");
        assert_eq!(events[0].data["line"], json!("hello"));
    }

    #[test]
    fn parse_discards_keepalives() {
        let events = parse(&[
            ": keepalive",
            "event: log",
            "data: {\"line\": \"x\"}",
            "",
            ": keepalive",
        ])
        .unwrap();
        assert_eq!(events.len(), 1);
    }

    #[test]
    fn parse_joins_multiline_data() {
        // Two data lines join with a newline into one payload; the platform
        // sends one object per event, so a joined pair of objects is the
        // documented failure path.
        assert!(matches!(
            parse(&["data: {\"line\": \"a\"}", "data: {\"line\": \"b\"}", ""]),
            Err(Error::Freepod(_))
        ));
    }

    #[test]
    fn parse_reports_an_unparseable_event() {
        assert!(matches!(
            parse(&["data: not json", ""]),
            Err(Error::Freepod(_))
        ));
    }

    #[test]
    fn format_timestamp_never_touches_a_float() {
        assert_eq!(
            format_timestamp(&json!("1700000000000000000")),
            "2023-11-14T22:13:20.000000000Z"
        );
        assert_eq!(format_timestamp(&json!("")), "-");
        assert_eq!(format_timestamp(&json!("not a number")), "-");
        assert_eq!(format_timestamp(&Value::Null), "-");
    }

    #[test]
    fn format_line_prefixes_the_timestamp_only_when_asked() {
        let data = json!({ "line": "hello", "ts": "1700000000000000000" });
        assert_eq!(format_line(&data, false), "hello");
        assert_eq!(
            format_line(&data, true),
            "2023-11-14T22:13:20.000000000Z hello"
        );
    }
}
