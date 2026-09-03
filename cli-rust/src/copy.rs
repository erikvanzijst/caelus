//! Copying files between the local machine and a deployment.
//!
//! Spec: openspec/specs/cli-ssh-access/spec.md · Rationale:
//! openspec/changes/unified-ssh-sidecar/design.md § D5.

use std::path::{Path, PathBuf};

use crate::errors::{freepod, usage, Result};

/// What marks a path as the deployment's. A bare colon, or the deployment's own
/// name and one — a *prefix* rule, so a local file called `notes:draft.txt` is
/// never mistaken for a remote path (D5).
const MARKER: &str = ":";

/// Characters the far end's batch parser would otherwise read as syntax. sftp
/// globs its arguments, so a local file holding `[` or `*` needs escaping too.
const ESCAPE: &str = "\\\"*?[";

/// Split `path` on the first `MARKER`, the way `str.partition` does: the part
/// before it, the marker itself, and the part after.
fn partition(path: &str) -> (&str, &str, &str) {
    match path.find(MARKER) {
        Some(i) => (&path[..i], MARKER, &path[i + MARKER.len()..]),
        None => (path, "", ""),
    }
}

/// The remote path `path` names, or `None` when it names a local one.
fn split_marker<'a>(path: &'a str, deployment: &str) -> Option<&'a str> {
    if let Some(rest) = path.strip_prefix(MARKER) {
        return Some(rest);
    }
    path.strip_prefix(&format!("{deployment}{MARKER}"))
}

/// The name in a `<name>:` prefix, when the path plausibly carries one.
///
/// Only ever used to explain a refusal. A path whose colon follows a path
/// separator is somebody's file, not a mis-typed deployment.
fn named_deployment(path: &str) -> Option<&str> {
    let (head, sep, _rest) = partition(path);
    if sep.is_empty() || head.is_empty() || head.contains('/') {
        return None;
    }
    Some(head)
}

/// One copy's resolved endpoints.
#[derive(Debug)]
pub struct Direction {
    pub local: String,
    pub remote: String,
    pub upload: bool,
}

/// `(local, remote, upload)` for one copy, or a refusal naming the ambiguity.
///
/// Exactly one side is the deployment's, and which one decides the direction —
/// there is no flag to set inconsistently with the paths.
pub fn direction(source: &str, destination: &str, deployment: &str) -> Result<Direction> {
    let remote_source = split_marker(source, deployment);
    let remote_destination = split_marker(destination, deployment);

    if remote_source.is_some() && remote_destination.is_some() {
        return Err(usage(
            "both paths name the deployment, and `freepod cp` does not copy \
             between deployments.\n  Mark exactly one side with ':'.",
        ));
    }
    if remote_source.is_none() && remote_destination.is_none() {
        for (side, path) in [("source", source), ("destination", destination)] {
            if let Some(named) = named_deployment(path) {
                let rest = partition(path).2;
                return Err(usage(format!(
                    "the {side} '{path}' names '{named}', which is not this \
                     project's deployment '{deployment}'.\n  This command acts \
                     on '{deployment}' alone; write ':{rest}' to name it.",
                )));
            }
        }
        return Err(usage(
            "neither path names the deployment, so this is a local copy your \
             own shell already does.\n  Mark the deployment's side with ':', \
             as in `freepod cp report.csv :/app/report.csv`.",
        ));
    }
    if let Some(remote) = remote_source {
        return Ok(Direction {
            local: destination.to_string(),
            remote: remote.to_string(),
            upload: false,
        });
    }
    Ok(Direction {
        local: source.to_string(),
        remote: remote_destination.expect("exactly one side is marked").to_string(),
        upload: true,
    })
}

/// The refusals visible without a connection, made before spending one.
///
/// A predictable failure should not cost a round trip, and should not read as
/// a platform problem.
pub fn check_local(local: &str, upload: bool) -> Result<()> {
    let path = Path::new(local);
    if upload {
        if !path.exists() {
            return Err(freepod(format!(
                "'{local}' does not exist on this machine, so there is nothing \
                 to copy.",
            )));
        }
        return Ok(());
    }
    // The directory that must already exist: the file's parent, or the path
    // itself when it names a directory.
    let parent = if path.is_dir() {
        path.to_path_buf()
    } else {
        match path.parent() {
            Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
            _ => PathBuf::from("."),
        }
    };
    if !parent.exists() {
        return Err(freepod(format!(
            "'{}' does not exist on this machine, so nothing can be written \
             there.",
            parent.display(),
        )));
    }
    Ok(())
}

/// One path as a single sftp batch argument, syntax and globbing disarmed.
pub fn quote(path: &str) -> String {
    let mut out = String::with_capacity(path.len() + 2);
    out.push('"');
    for c in path.chars() {
        if ESCAPE.contains(c) {
            out.push('\\');
        }
        out.push(c);
    }
    out.push('"');
    out
}

/// The one sftp batch line that carries the copy.
///
/// `-r` is always given and never asked for: the protocol recurses, a single
/// file is unaffected by it, and `kubectl cp` — one container you own — has no
/// such flag either. It is not `-p`: that would preserve timestamps as well as
/// modes, and only modes are promised.
pub fn batch(local: &str, remote: &str, upload: bool) -> String {
    let verb = if upload { "put" } else { "get" };
    let (first, second) = if upload { (local, remote) } else { (remote, local) };
    format!("{verb} -r {} {}\n", quote(first), quote(second))
}

/// Drive one transfer, returning sftp's own exit code.
///
/// stderr is the user's, so whatever sftp said about a path it could not read
/// reaches them as it was written. Its stdout is not: in batch mode that is the
/// script echoed back and a line per directory entered, which is this command's
/// own plumbing rather than anything the user asked to see.
pub fn run(args: &[String], script: &str) -> Result<i32> {
    crate::ssh::run_sftp(args, script)
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- which side is the deployment's ------------------------------------

    #[test]
    fn a_marked_source_is_an_upload() {
        let d = direction("report.csv", ":/app/report.csv", "myapp").unwrap();
        assert_eq!(d.local, "report.csv");
        assert_eq!(d.remote, "/app/report.csv");
        assert!(d.upload);
    }

    #[test]
    fn a_marked_destination_is_a_download() {
        let d = direction(":/app/out.log", "out.log", "myapp").unwrap();
        assert_eq!(d.local, "out.log");
        assert_eq!(d.remote, "/app/out.log");
        assert!(!d.upload);
    }

    #[test]
    fn the_long_form_names_this_deployment() {
        let d = direction("myapp:/app/out.log", "out.log", "myapp").unwrap();
        assert_eq!(d.local, "out.log");
        assert_eq!(d.remote, "/app/out.log");
        assert!(!d.upload);
    }

    #[test]
    fn a_local_path_with_a_colon_stays_local() {
        let d = direction("notes:draft.txt", ":/app/notes.txt", "myapp").unwrap();
        assert_eq!(d.local, "notes:draft.txt");
        assert_eq!(d.remote, "/app/notes.txt");
        assert!(d.upload);
    }

    #[test]
    fn both_sides_marked_is_refused() {
        let err = direction(":/app/a", ":/app/b", "myapp").unwrap_err();
        assert_eq!(err.exit_code(), crate::errors::EXIT_USAGE);
        assert!(err.message().contains("does not copy between deployments"));
    }

    #[test]
    fn neither_side_marked_is_refused() {
        let err = direction("a.txt", "b.txt", "myapp").unwrap_err();
        assert_eq!(err.exit_code(), crate::errors::EXIT_USAGE);
        assert!(err.message().contains("neither path names the deployment"));
    }

    #[test]
    fn a_marked_other_deployment_is_refused() {
        let err = direction("other-app:/app/out.log", "out.log", "myapp").unwrap_err();
        assert_eq!(err.exit_code(), crate::errors::EXIT_USAGE);
        let msg = err.message();
        assert!(msg.contains("other-app"));
        assert!(msg.contains("myapp"));
    }

    // --- the refusals made before a connection -----------------------------

    #[test]
    fn a_missing_upload_source_is_refused() {
        let base = std::env::temp_dir().join(format!("freepod-copy-missing-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        let src = base.join("absent.txt");
        let err = check_local(&src.display().to_string(), true).unwrap_err();
        assert_eq!(err.exit_code(), crate::errors::EXIT_ERROR);
        assert!(err.message().contains("does not exist on this machine"));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn an_unwritable_download_destination_is_refused() {
        let base = std::env::temp_dir().join(format!("freepod-copy-nowhere-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        let dst = base.join("no/such/dir/out.log");
        let err = check_local(&dst.display().to_string(), false).unwrap_err();
        assert_eq!(err.exit_code(), crate::errors::EXIT_ERROR);
        assert!(err.message().contains("nothing can be written there"));
        let _ = std::fs::remove_dir_all(&base);
    }

    // --- the batch script ----------------------------------------------------

    #[test]
    fn the_transfer_always_recurses_and_never_preserves_timestamps() {
        let line = batch("tree", "/app/tree", true);
        assert!(line.starts_with("put -r "));
        assert!(!line.contains(" -p "));
    }

    #[test]
    fn a_path_holding_syntax_reaches_the_far_end_whole() {
        let input = r#"od[d] "name"*.txt"#;
        let quoted = quote(input);
        assert!(quoted.starts_with('"') && quoted.ends_with('"'));
        for character in ['\\', '"', '*', '?', '['] {
            if input.contains(character) {
                let escaped = format!("\\{character}");
                assert!(quoted.contains(escaped.as_str()));
            }
        }
    }
}
