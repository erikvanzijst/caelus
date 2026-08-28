//! Turning a project directory into a deterministic tar.gz stream.
//!
//! Four levels of ignore precedence, last match wins:
//!
//! 1. **Hard excludes**, never overridable: `.git/`.
//! 2. **Built-in defaults**: dependency, build-output, cache, and editor
//!    artifacts.
//! 3. **`.gitignore`**, honored by default including nested ones.
//! 4. **`.freepodignore`**, applied last, so `!` negations can re-include
//!    anything except a hard exclude.
//!
//! Matching is the `ignore` crate's gitignore matcher; the walk is ours. The
//! walk owns the two things the matcher does not do: per-directory layering
//! (git evaluates each `.gitignore` relative to its own directory, so we carry
//! a stack of specs rewritten relative to the project root) and **pruning** —
//! not descending into an excluded directory.
//!
//! Pruning is not merely an optimization. The matcher and git genuinely
//! disagree about `node_modules/` followed by `!node_modules/keep.txt`: git
//! reports `keep.txt` as ignored, the matcher re-includes it. Pruning yields
//! git's answer, which is the one a user can hold in their head. The idiom
//! that does work is documented in the README:
//!
//! ```
//! node_modules/*            <- exclude the entries, not the directory itself
//! !node_modules/keep.txt    <- re-inclusion now applies
//! ```
//!
//! Mirrors `archive.py`.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use flate2::Compression;
use flate2::write::GzEncoder;
use ignore::gitignore::{Gitignore, GitignoreBuilder};
use tar::{Builder, EntryType, Header};

use crate::project::PROJECT_FILE;

/// A hook invoked for each path the packer skips, with the path and the reason.
pub type SkipHook = Option<Box<dyn Fn(&str, &str)>>;

/// The packed archive: its bytes, its size, and the members it holds.
pub type PackResult = std::io::Result<(Vec<u8>, usize, Vec<(String, PathBuf)>)>;

/// Never overridable, not even by a `.freepodignore` negation. Uploading a
/// repository's history is never intended and is frequently enormous.
pub const HARD_EXCLUDES: &[&str] = &[".git/"];

/// Always applied, ahead of the project's own ignore files so that either can
/// override them. `.env` is deliberately absent.
pub const DEFAULT_EXCLUDES: &[&str] = &[
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    "target/",
    "dist/",
    "build/",
    ".DS_Store",
    "*.swp",
    ".env.local",
    ".env.*.local",
];

pub const GITIGNORE_FILE: &str = ".gitignore";
pub const FREEPODIGNORE_FILE: &str = ".freepodignore";

/// One ignore file's patterns, rewritten relative to the project root.
///
/// The negation bodies are kept alongside the compiled spec because pruning
/// needs a question the matcher cannot answer: *could* anything below this
/// directory be re-included by a later negation?
#[derive(Clone)]
struct Layer {
    spec: Gitignore,
    negations: Vec<String>,
}

/// A stack of layers, evaluated last-match-wins as git does.
#[derive(Clone)]
struct Ignores {
    layers: Vec<Layer>,
}

impl Ignores {
    fn new(layers: Vec<Layer>) -> Self {
        Self { layers }
    }

    /// Whether a path is excluded, last match wins across the layers.
    fn excluded(&self, relative: &str, is_dir: bool) -> bool {
        let mut verdict = false;
        for layer in &self.layers {
            let m = layer.spec.matched(relative, is_dir);
            if !m.is_none() {
                verdict = m.is_ignore();
            }
        }
        verdict
    }

    /// Whether any layer negates a path beneath `directory`.
    fn negates_under(&self, directory: &str) -> bool {
        let prefix = format!("{}/", directory.trim_end_matches('/'));
        for layer in &self.layers {
            for body in &layer.negations {
                if body.starts_with(&prefix) {
                    return true;
                }
            }
        }
        false
    }

    fn extend(&self, layer: Option<Layer>) -> Ignores {
        match layer {
            Some(l) => {
                let mut layers = self.layers.clone();
                layers.push(l);
                Ignores::new(layers)
            }
            None => self.clone(),
        }
    }
}

/// The root-relative paths a layer's `!` patterns could re-include.
fn negation_bodies(patterns: &[String], base: &str) -> Vec<String> {
    let mut bodies = Vec::new();
    for raw in patterns {
        let stripped = raw.trim();
        if !stripped.starts_with('!') {
            continue;
        }
        let body = stripped[1..].trim_start_matches('/');
        if body.is_empty() {
            continue;
        }
        bodies.push(if base.is_empty() {
            body.to_string()
        } else {
            format!("{base}/{body}")
        });
    }
    bodies
}

/// Re-anchor a directory's ignore patterns onto the project root.
///
/// git evaluates a `.gitignore` relative to the directory containing it. A
/// pattern with no separator matches at any depth *below* that directory; one
/// with a separator is anchored to it. Both become root-relative here so a
/// single spec can judge a root-relative path.
fn rewrite(patterns: &[String], base: &str) -> Vec<String> {
    if base.is_empty() {
        return patterns.to_vec();
    }

    let mut rewritten = Vec::new();
    for raw in patterns {
        let line = raw.trim_end_matches('\n');
        let stripped = line.trim();
        if stripped.is_empty() || stripped.starts_with('#') {
            rewritten.push(line.to_string());
            continue;
        }

        let negated = stripped.starts_with('!');
        let body = if negated {
            &stripped[1..]
        } else {
            stripped
        };

        // A trailing separator marks directory-only; a leading one anchors.
        let anchored = body.trim_end_matches('/').contains('/');
        let body = if body.starts_with('/') {
            body.trim_start_matches('/')
        } else {
            body
        };

        let prefix = format!("{base}/");
        let sign = if negated { "!" } else { "" };
        if anchored {
            rewritten.push(format!("{sign}{prefix}{body}"));
        } else {
            // Unanchored: matches at any depth under this directory.
            rewritten.push(format!("{sign}{prefix}{body}"));
            rewritten.push(format!("{sign}{prefix}**/{body}"));
        }
    }
    rewritten
}

/// Build a matcher from root-relative pattern lines. Parse errors are skipped,
/// matching the lenient reference behavior.
fn spec(patterns: &[String]) -> Gitignore {
    let mut builder = GitignoreBuilder::new(".");
    for line in patterns {
        let _ = builder.add_line(None, line);
    }
    builder.build().unwrap_or_else(|_| Gitignore::empty())
}

/// Read one ignore file into a layer, or None if it is absent or empty.
fn read_ignore_file(path: &Path, base: &str) -> Option<Layer> {
    let text = fs::read_to_string(path).ok()?;
    let lines: Vec<String> = text.lines().map(|l| l.to_string()).collect();
    let patterns = rewrite(&lines, base);
    if patterns.is_empty() {
        return None;
    }
    Some(Layer {
        spec: spec(&patterns),
        negations: negation_bodies(&lines, base),
    })
}

/// Walks a project root and emits the members that belong in the archive.
pub struct Packer {
    root: PathBuf,
    honor_gitignore: bool,
    on_skip: SkipHook,
    pub skipped: Vec<(String, String)>,
    hard: Gitignore,
    defaults: Gitignore,
    freepodignore: Option<Layer>,
}

impl Packer {
    pub fn new(
        root: impl Into<PathBuf>,
        honor_gitignore: bool,
        on_skip: SkipHook,
    ) -> Self {
        let root = root.into();
        let root = root
            .canonicalize()
            .unwrap_or_else(|_| root.clone());

        let freepodignore_path = root.join(FREEPODIGNORE_FILE);
        let freepodignore = if freepodignore_path.is_file() {
            read_ignore_file(&freepodignore_path, "")
        } else {
            None
        };

        Self {
            root,
            honor_gitignore,
            on_skip,
            skipped: Vec::new(),
            hard: spec(HARD_EXCLUDES.iter().map(|s| s.to_string()).collect::<Vec<_>>().as_slice()),
            defaults: spec(
                DEFAULT_EXCLUDES
                    .iter()
                    .map(|s| s.to_string())
                    .collect::<Vec<_>>()
                    .as_slice(),
            ),
            freepodignore,
        }
    }

    fn matches(spec: &Gitignore, relative: &str, is_dir: bool) -> bool {
        spec.matched(relative, is_dir).is_ignore()
    }

    fn stack(&self, ignores: &Ignores) -> Ignores {
        ignores.extend(self.freepodignore.clone())
    }

    /// Whether a *file* is excluded, last match wins across all four levels.
    fn excluded(&self, ignores: &Ignores, relative: &str, is_dir: bool) -> bool {
        // `.freepod.json` is included unconditionally: it holds no secrets, and
        // a project whose own descriptor was missing from its build would be a
        // baffling failure.
        if relative == PROJECT_FILE {
            return false;
        }
        if Self::matches(&self.hard, relative, is_dir) {
            return true;
        }

        let mut verdict = Self::matches(&self.defaults, relative, is_dir);
        for layer in self.stack(ignores).layers.iter() {
            let m = layer.spec.matched(relative, is_dir);
            if !m.is_none() {
                verdict = m.is_ignore();
            }
        }
        verdict
    }

    /// Whether to skip descending into a directory entirely.
    fn prunes(&self, ignores: &Ignores, relative: &str) -> bool {
        if Self::matches(&self.hard, relative, true) {
            return true;
        }

        let stack = self.stack(ignores);
        if stack.excluded(relative, true) {
            return true;
        }

        if Self::matches(&self.defaults, relative, true) {
            return !stack.negates_under(relative);
        }

        false
    }

    /// Every included member, as (archive path, filesystem path), sorted.
    pub fn members(&mut self) -> Vec<(String, PathBuf)> {
        let mut found: Vec<(String, PathBuf)> = Vec::new();
        let base = Ignores::new(Vec::new());
        let root = self.root.clone();
        self.walk(&root, "", &base, &mut found);
        found.sort_by(|a, b| a.0.cmp(&b.0));
        found
    }

    fn layer_for(&self, directory: &Path, base: &str) -> Option<Layer> {
        if !self.honor_gitignore {
            return None;
        }
        let candidate = directory.join(GITIGNORE_FILE);
        if !candidate.is_file() {
            return None;
        }
        read_ignore_file(&candidate, base)
    }

    fn walk(
        &mut self,
        directory: &Path,
        base: &str,
        ignores: &Ignores,
        found: &mut Vec<(String, PathBuf)>,
    ) {
        let ignores = ignores.extend(self.layer_for(directory, base));

        let entries = match read_dir_sorted(directory) {
            Ok(e) => e,
            Err(e) => {
                self.skip(if base.is_empty() { "." } else { base }, &format!("cannot read directory: {e}"));
                return;
            }
        };

        for (name, path) in entries {
            let relative = if base.is_empty() {
                name.clone()
            } else {
                format!("{base}/{name}")
            };

            let Ok(meta) = fs::symlink_metadata(&path) else {
                self.skip(&relative, "cannot stat");
                continue;
            };
            let file_type = meta.file_type();
            let is_dir = file_type.is_dir();
            let is_file = file_type.is_file();
            let is_link = file_type.is_symlink();

            if is_dir {
                if self.prunes(&ignores, &relative) {
                    // Pruned, not walked-and-filtered. This is both the
                    // performance win and the thing that makes a negation
                    // unable to reach inside, matching git.
                    continue;
                }
                self.walk(&path, &relative, &ignores, found);
                continue;
            }

            if self.excluded(&ignores, &relative, false) {
                continue;
            }

            if is_link {
                if !self.link_stays_inside(&path) {
                    self.skip(&relative, "symlink resolves outside the project");
                    continue;
                }
                found.push((relative, path));
                continue;
            }

            if !is_file {
                self.skip(&relative, &describe_special(&path));
                continue;
            }

            found.push((relative, path));
        }
    }

    fn link_stays_inside(&self, path: &Path) -> bool {
        let Ok(resolved) = path.canonicalize() else {
            return false;
        };
        resolved.starts_with(&self.root)
    }

    fn skip(&mut self, relative: &str, reason: &str) {
        self.skipped.push((relative.to_string(), reason.to_string()));
        if let Some(cb) = &self.on_skip {
            cb(relative, reason);
        }
    }
}

/// The directory's entries as (name, path), sorted by name.
fn read_dir_sorted(directory: &Path) -> std::io::Result<Vec<(String, PathBuf)>> {
    let mut out: Vec<(String, PathBuf)> = Vec::new();
    for rd in fs::read_dir(directory)? {
        let rd = rd?;
        let name = rd.file_name().to_string_lossy().into_owned();
        out.push((name, rd.path()));
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(out)
}

fn describe_special(path: &Path) -> String {
    use std::os::unix::fs::MetadataExt;
    let Ok(meta) = fs::symlink_metadata(path) else {
        return "unreadable special file".to_string();
    };
    let mode = meta.mode();
    if mode & 0o170000 == 0o140000 {
        "socket".to_string()
    } else if mode & 0o170000 == 0o010000 {
        "FIFO".to_string()
    } else if mode & 0o170000 == 0o060000 || mode & 0o170000 == 0o020000 {
        "device node".to_string()
    } else {
        "not a regular file".to_string()
    }
}

/// Strip everything that would differ between two machines: ownership is
/// zeroed, account names blanked, and the mode normalized to the two states
/// extraction cares about.
fn normalize_mode(mode: u32) -> u32 {
    if mode & 0o100 != 0 {
        0o755
    } else {
        0o644
    }
}

/// Pack `root` into a gzip-compressed tar.
///
/// Returns `(bytes, size, members)`. The archive is materialized rather than
/// streamed: the presigned POST's policy carries a `content-length-range`
/// condition the store evaluates against the request, and a stream cannot be
/// retried — re-packing a tree that may have changed produces a different
/// archive.
pub fn pack(
    root: impl Into<PathBuf>,
    honor_gitignore: bool,
    on_skip: SkipHook,
) -> PackResult {
    let mut packer = Packer::new(root, honor_gitignore, on_skip);
    let members = packer.members();

    let mut builder = Builder::new(Vec::new());
    for (relative, path) in &members {
        append_member(&mut builder, relative, path)?;
    }
    let tar_bytes = builder.into_inner()?;

    // gzip with mtime 0 so two packs of an unchanged tree agree byte for byte.
    let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
    encoder.write_all(&tar_bytes)?;
    let bytes = encoder.finish()?;
    let size = bytes.len();
    Ok((bytes, size, members))
}

fn append_member(
    builder: &mut Builder<Vec<u8>>,
    relative: &str,
    path: &Path,
) -> std::io::Result<()> {
    let meta = fs::symlink_metadata(path)?;
    let file_type = meta.file_type();

    if file_type.is_symlink() {
        let target = fs::read_link(path)?;
        let mut header = Header::new_gnu();
        header.set_entry_type(EntryType::symlink());
        header.set_size(0);
        header.set_mode(0o777);
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(0);
        header.set_link_name(target)?;
        header.set_cksum();
        builder.append_data(&mut header, relative, &b""[..])?;
        return Ok(());
    }

    if file_type.is_dir() {
        let mut header = Header::new_gnu();
        header.set_entry_type(EntryType::dir());
        header.set_size(0);
        header.set_mode(0o755);
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(0);
        header.set_cksum();
        builder.append_data(&mut header, relative, &b""[..])?;
        return Ok(());
    }

    // Regular file.
    let bytes = fs::read(path)?;
    use std::os::unix::fs::MetadataExt;
    let mode = meta.mode();
    let mut header = Header::new_gnu();
    header.set_entry_type(EntryType::file());
    header.set_size(bytes.len() as u64);
    header.set_mode(normalize_mode(mode));
    header.set_uid(0);
    header.set_gid(0);
    header.set_mtime(0);
    header.set_cksum();
    builder.append_data(&mut header, relative, &bytes[..])?;
    Ok(())
}

/// Announce the packed size, and under `--verbose` the biggest entries.
pub fn report(
    size: usize,
    members: &[(String, PathBuf)],
    verbose: bool,
    echo: &dyn Fn(&str),
) {
    let plural = if members.len() == 1 { "" } else { "s" };
    echo(&format!("Packed {} file{plural}, {}.", members.len(), human(size as u64)));
    if !verbose {
        return;
    }
    for (name, entry_size) in largest(members, 10) {
        echo(&format!("    {:>10}  {name}", human(entry_size as u64)));
    }
}

/// The biggest members by on-disk size, for `--verbose`.
pub fn largest(members: &[(String, PathBuf)], count: usize) -> Vec<(String, usize)> {
    let mut sized: Vec<(String, usize)> = Vec::new();
    for (relative, path) in members {
        if let Ok(meta) = fs::metadata(path) {
            sized.push((relative.clone(), meta.len() as usize));
        }
    }
    sized.sort_by_key(|a| std::cmp::Reverse(a.1));
    sized.truncate(count);
    sized
}

/// A byte count the way the reference renders it.
pub fn human(size: u64) -> String {
    let mut value = size as f64;
    for unit in ["B", "KiB", "MiB", "GiB"] {
        if value < 1024.0 || unit == "GiB" {
            return if unit == "B" {
                format!("{value:.0} {unit}")
            } else {
                format!("{value:.1} {unit}")
            };
        }
        value /= 1024.0;
    }
    unreachable!()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pack_roundtrip() {
        let dir = tempfile_dir();
        fs::create_dir_all(dir.join("src")).unwrap();
        fs::write(dir.join("src/hello.txt"), b"hello world").unwrap();
        fs::write(dir.join("run.sh"), b"#!/bin/sh\necho hi\n").unwrap();
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir.join("run.sh"), fs::Permissions::from_mode(0o755)).unwrap();
        fs::create_dir_all(dir.join("build")).unwrap();
        fs::write(dir.join("build/out.bin"), b"junk").unwrap();
        fs::write(dir.join(".gitignore"), b"build/\n").unwrap();

        let (bytes, size, members) = pack(&dir, true, None).unwrap();
        assert!(size == bytes.len() && size > 0);
        let names: Vec<String> = members.iter().map(|(n, _)| n.clone()).collect();
        assert_eq!(names, vec![".gitignore", "run.sh", "src/hello.txt"]);

        // Read the gzip back and confirm the tar members and their content.
        use std::io::Read;
        let mut dec = flate2::read::GzDecoder::new(&bytes[..]);
        let mut tar_bytes = Vec::new();
        dec.read_to_end(&mut tar_bytes).unwrap();
        let mut ar = tar::Archive::new(&tar_bytes[..]);
        let mut seen = std::collections::HashMap::new();
        for entry in ar.entries().unwrap() {
            let mut e = entry.unwrap();
            let name = e.path().unwrap().to_string_lossy().into_owned();
            let mode = e.header().mode().unwrap();
            if e.header().entry_type().is_file() {
                let mut buf = Vec::new();
                e.read_to_end(&mut buf).unwrap();
                seen.insert(name.clone(), (mode, buf));
            } else {
                seen.insert(name.clone(), (mode, Vec::new()));
            }
        }
        assert_eq!(seen.get("src/hello.txt").unwrap().1, b"hello world");
        assert_eq!(seen.get("run.sh").unwrap().1, b"#!/bin/sh\necho hi\n");
        assert_eq!(seen.get("run.sh").unwrap().0, 0o755);
        assert_eq!(seen.get("src/hello.txt").unwrap().0, 0o644);
        assert!(!seen.contains_key("build/out.bin"));
    }

    fn tempfile_dir() -> PathBuf {
        let mut d = std::env::temp_dir();
        d.push(format!("freepod-archive-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn dir_only_patterns_use_the_flag() {
        // A directory-only pattern (`build/`) matches a directory via the
        // `is_dir` flag, not a trailing slash: the matcher returns no match for
        // a slashed path, which is why every call site passes the bare path.
        let lines = ["build/", "*.log"];
        let gi = spec(&lines.iter().map(|s| s.to_string()).collect::<Vec<_>>());
        assert!(gi.matched("build", true).is_ignore());
        assert!(gi.matched("build/", true).is_none());
        assert!(gi.matched("build", false).is_none());
        assert!(gi.matched("app.log", false).is_ignore());
    }

    /// Differential hook: with `ARCHIVE_DIFF_DIR` set, print the member names
    /// (one per line) so a shell script can diff them against the Python
    /// reference. Skipped when the variable is unset.
    #[test]
    fn diff_members() {
        let dir = match std::env::var("ARCHIVE_DIFF_DIR") {
            Ok(d) => d,
            Err(_) => return,
        };
        let mut packer = Packer::new(PathBuf::from(dir), true, None);
        for (name, _) in packer.members() {
            println!("{name}");
        }
    }
}
