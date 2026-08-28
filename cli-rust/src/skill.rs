//! `freepod skill` — install the packaged agent instructions for this client.
//!
//! Mirrors `skill.py`. The skill is shipped as packaged data rather than as
//! documentation in the repository, because the copy an agent reads has to be
//! versioned with the client it drives. `cargo install --force` followed by
//! `freepod skill install` is the whole update story.
//!
//! `SKILL.md` with YAML frontmatter is a cross-agent format: Claude Code,
//! Codex, OpenCode, Amp and Gemini all read the same file, differing only in
//! where they look for it. So one document serves every agent and this module
//! is only a table of directories.
//!
//! **That table is the part that will go stale.** When an agent's path moves,
//! correct the row; `--dest` exists so that a user is never blocked waiting
//! for that release.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use crate::errors::{freepod, usage, Result};

pub const SKILL_NAME: &str = "deploy-to-freepod";
pub const SKILL_FILE: &str = "SKILL.md";

/// One coding agent: how to notice it, and where its skills live.
#[derive(Clone)]
pub struct Agent {
    pub key: &'static str,
    pub label: &'static str,
    /// Presence of this directory is what "installed on this machine" means.
    /// It is the agent's configuration directory, not its skills directory:
    /// an agent the user has run but never given a skill to still counts.
    pub config_dir: PathBuf,
    pub user_skills: PathBuf,
    /// Relative to the project root, for `--project`.
    pub project_skills: PathBuf,
}

fn home() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/"))
}

/// `$XDG_CONFIG_HOME`, or the `~/.config` it defaults to.
fn config_home() -> PathBuf {
    std::env::var("XDG_CONFIG_HOME")
        .ok()
        .map(PathBuf::from)
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| home().join(".config"))
}

fn dir_from_env(variable: &str, fallback: PathBuf) -> PathBuf {
    std::env::var(variable)
        .ok()
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or(fallback)
}

/// The supported agents, in a stable order.
///
/// Built per call rather than at startup so the environment variables and the
/// home directory are read when the command runs.
pub fn agents() -> Vec<Agent> {
    let home = home();
    let config = config_home();

    // Amp is the one row whose install path is not under its own config
    // directory: it reads user-level skills from `~/.config/agents/skills`,
    // while `~/.config/amp` is what tells us Amp is installed at all.
    let claude_base = dir_from_env("CLAUDE_CONFIG_DIR", home.join(".claude"));
    let codex_base = dir_from_env("CODEX_HOME", home.join(".codex"));

    vec![
        Agent {
            key: "claude",
            label: "Claude Code",
            config_dir: claude_base.clone(),
            user_skills: claude_base.join("skills"),
            project_skills: PathBuf::from(".claude/skills"),
        },
        Agent {
            key: "codex",
            label: "Codex",
            // `$CODEX_HOME/skills/<name>`, per Codex's own bundled
            // skill-installer skill.
            config_dir: codex_base.clone(),
            user_skills: codex_base.join("skills"),
            project_skills: PathBuf::from(".codex/skills"),
        },
        Agent {
            key: "opencode",
            label: "OpenCode",
            config_dir: config.join("opencode"),
            user_skills: config.join("opencode").join("skills"),
            project_skills: PathBuf::from(".opencode/skills"),
        },
        Agent {
            key: "amp",
            label: "Amp",
            config_dir: config.join("amp"),
            user_skills: config.join("agents").join("skills"),
            project_skills: PathBuf::from(".agents/skills"),
        },
        Agent {
            key: "gemini",
            label: "Gemini CLI",
            config_dir: home.join(".gemini"),
            user_skills: home.join(".gemini").join("skills"),
            project_skills: PathBuf::from(".gemini/skills"),
        },
    ]
}

pub fn agent_keys() -> Vec<String> {
    agents().iter().map(|a| a.key.to_string()).collect()
}

/// Resolve `--agent`/`--all` to a list, or fall back to what is installed.
pub fn select(names: &[String], everything: bool) -> Result<Vec<Agent>> {
    let all = agents();
    let known: HashMap<&str, &Agent> =
        all.iter().map(|a| (a.key, a)).collect();
    let known_keys: Vec<String> = all.iter().map(|a| a.key.to_string()).collect();

    if everything {
        return Ok(all);
    }

    if !names.is_empty() {
        let mut chosen: Vec<Agent> = Vec::new();
        for name in names {
            let key = name.trim().to_lowercase();
            let Some(agent) = known.get(key.as_str()) else {
                return Err(usage(format!(
                    "unknown agent '{name}'. Known agents: {}.",
                    known_keys.join(", ")
                )));
            };
            if !chosen.iter().any(|c| c.key == agent.key) {
                chosen.push((*agent).clone());
            }
        }
        return Ok(chosen);
    }

    Ok(all
        .into_iter()
        .filter(|agent| agent.config_dir.is_dir())
        .collect())
}

pub fn target_for(agent: &Agent, project: bool) -> PathBuf {
    let root = if project {
        &agent.project_skills
    } else {
        &agent.user_skills
    };
    root.join(SKILL_NAME).join(SKILL_FILE)
}

/// Return the packaged SKILL.md.
pub fn read_skill() -> &'static str {
    include_str!("assets/SKILL.md")
}

/// Write the skill to `target`, overwriting whatever is there.
///
/// There is no confirmation and no `--force`, by design: this path belongs to
/// the client, the file is generated rather than authored, and the upgrade
/// story only works if a newer client can replace an older skill without
/// ceremony. An unchanged file is reported rather than rewritten, so a re-run
/// is quiet and the mtime keeps meaning something.
pub fn write(target: &Path, content: Option<&str>) -> Result<String> {
    let content = content.unwrap_or(read_skill());

    if target.exists() {
        match std::fs::read_to_string(target) {
            Ok(existing) if existing == content => return Ok("current".to_string()),
            _ => {
                // Unreadable but present: fall through and replace it.
            }
        }
    }

    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| freepod(format!("cannot write {}: {e}", target.display())))?;
    }
    std::fs::write(target, content)
        .map_err(|e| freepod(format!("cannot write {}: {e}", target.display())))?;

    Ok("installed".to_string())
}

/// Resolve as much of `path` as exists, leaving the rest as-is — the
/// behaviour of Python's `Path.resolve()` on a path that does not yet exist.
fn resolve_lenient(path: &Path) -> PathBuf {
    let mut existing = path;
    let mut tail: Vec<std::ffi::OsString> = Vec::new();
    loop {
        match existing.canonicalize() {
            Ok(resolved) => {
                let mut result = resolved;
                for component in tail.iter().rev() {
                    result = result.join(component);
                }
                return result;
            }
            Err(_) => match existing.parent() {
                Some(parent) if !parent.as_os_str().is_empty() => {
                    if let Some(name) = existing.file_name() {
                        tail.push(name.to_os_string());
                    }
                    existing = parent;
                }
                _ => return path.to_path_buf(),
            },
        }
    }
}

/// Install for every agent in `chosen`, skipping duplicate destinations.
///
/// Two agents can resolve to one directory — several already read each
/// other's locations for compatibility, and a redirected `CLAUDE_CONFIG_DIR`
/// can do it outright. Writing twice would be harmless but reporting twice
/// would not be, so the first agent to claim a path owns it.
pub fn install(chosen: &[Agent], project: bool) -> Result<Vec<(Agent, PathBuf, String)>> {
    let content = read_skill();
    let mut seen: HashMap<PathBuf, ()> = HashMap::new();
    let mut results: Vec<(Agent, PathBuf, String)> = Vec::new();

    for agent in chosen {
        let target = target_for(agent, project);
        let parent = target
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_default();
        let resolved = resolve_lenient(&parent);
        if seen.contains_key(&resolved) {
            continue;
        }
        seen.insert(resolved, ());
        let outcome = write(&target, Some(content))?;
        results.push((agent.clone(), target, outcome));
    }

    Ok(results)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn select_rejects_an_unknown_agent() {
        assert!(matches!(
            select(&["nope".to_string()], false),
            Err(crate::errors::Error::Usage(_))
        ));
    }

    #[test]
    fn select_dedupes_repeated_names() {
        let chosen = select(&["claude".to_string(), "claude".to_string()], false).unwrap();
        assert_eq!(chosen.len(), 1);
        assert_eq!(chosen[0].key, "claude");
    }

    #[test]
    fn select_accepts_names_case_insensitively() {
        let chosen = select(&["Claude".to_string()], false).unwrap();
        assert_eq!(chosen[0].key, "claude");
    }

    #[test]
    fn select_all_returns_every_agent_in_order() {
        let chosen = select(&[], true).unwrap();
        assert_eq!(
            chosen.iter().map(|a| a.key).collect::<Vec<_>>(),
            vec!["claude", "codex", "opencode", "amp", "gemini"]
        );
    }

    #[test]
    fn write_reports_current_when_unchanged() {
        let dir = std::env::temp_dir().join(format!("freepod-skill-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let target = dir.join("nested").join(SKILL_FILE);
        assert_eq!(write(&target, Some("content")).unwrap(), "installed");
        assert_eq!(write(&target, Some("content")).unwrap(), "current");
        assert_eq!(write(&target, Some("other")).unwrap(), "installed");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn install_skips_duplicate_destinations() {
        // Point two agents at one directory through the environment.
        let dir = std::env::temp_dir().join(format!("freepod-skill-dup-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::env::set_var("CLAUDE_CONFIG_DIR", &dir);
        let config = std::env::temp_dir().join(format!("freepod-skill-xdg-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&config);
        std::env::set_var("XDG_CONFIG_HOME", &config);
        // Amp's user skills live under $XDG_CONFIG_HOME/agents/skills; point
        // CLAUDE at the same place so both resolve to one directory.
        std::env::set_var("CLAUDE_CONFIG_DIR", config.join("agents"));
        let chosen = select(&["claude".to_string(), "amp".to_string()], false).unwrap();
        let results = install(&chosen, false).unwrap();
        assert_eq!(results.len(), 1);
        let _ = std::fs::remove_dir_all(&dir);
        let _ = std::fs::remove_dir_all(&config);
        std::env::remove_var("CLAUDE_CONFIG_DIR");
        std::env::remove_var("XDG_CONFIG_HOME");
    }
}
