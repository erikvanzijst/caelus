//! The `.freepod-rust.json` project file: load, save, and project-root discovery.
//!
//! Mirrors `project.py`. The file holds intent — the environment, the
//! deployment pointer, and the user values — and nothing a deploy would
//! rewrite. The Rust client uses a distinct filename so the two clients can
//! coexist in one project directory.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use serde_json::{json, Value};

use crate::errors::{freepod, usage, Result};

pub const PROJECT_FILE: &str = ".freepod-rust.json";

/// Bumped when the on-disk format changes incompatibly.
pub const FORMAT_VERSION: u64 = 1;

/// Keys a deploy produces rather than a user declaring. Stripped on write.
const BUILD_OUTPUT_KEYS: &[&str] = &["image"];

/// One project's file, and the directory it was found in.
#[derive(Debug, Clone)]
pub struct Project {
    pub root: PathBuf,
    pub env: String,
    pub user_values: HashMap<String, Value>,
    pub deployment: Option<HashMap<String, String>>,
    pub version: u64,
}

impl Project {
    pub fn new(
        root: PathBuf,
        env: impl Into<String>,
        user_values: HashMap<String, Value>,
    ) -> Self {
        Self {
            root,
            env: env.into(),
            user_values,
            deployment: None,
            version: FORMAT_VERSION,
        }
    }

    pub fn path(&self) -> PathBuf {
        self.root.join(PROJECT_FILE)
    }

    pub fn deployment_id(&self) -> Option<&str> {
        self.deployment.as_ref().and_then(|d| d.get("id").map(|s| s.as_str()))
    }
    pub fn deployment_name(&self) -> Option<&str> {
        self.deployment.as_ref().and_then(|d| d.get("name").map(|s| s.as_str()))
    }

    /// The document as written to disk.
    pub fn to_document(&self) -> Value {
        let values: HashMap<String, Value> = self
            .user_values
            .iter()
            .filter(|(k, _)| !BUILD_OUTPUT_KEYS.contains(&k.as_str()))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        json!({
            "version": self.version,
            "env": self.env,
            "deployment": self.deployment.as_ref().map(|d| {
                let mut obj = serde_json::Map::new();
                for (k, v) in d {
                    obj.insert(k.clone(), Value::String(v.clone()));
                }
                Value::Object(obj)
            }),
            "user_values": values,
        })
    }

    /// Write the file, atomically, with a trailing newline.
    pub fn save(&self) -> Result<()> {
        let document = self.to_document();
        let text = serde_json::to_string_pretty(&document)
            .map_err(|e| freepod(format!("cannot serialize project file: {e}")))?;
        let text = format!("{text}\n");
        let path = self.path();
        let pid = std::process::id();
        let temporary = path.with_file_name(format!("{PROJECT_FILE}.{pid}.tmp"));
        match std::fs::write(&temporary, text) {
            Ok(()) => std::fs::rename(&temporary, &path)
                .map_err(|e| {
                    let _ = std::fs::remove_file(&temporary);
                    freepod(format!("cannot write {}: {e}", path.display()))
                }),
            Err(e) => {
                let _ = std::fs::remove_file(&temporary);
                Err(freepod(format!("cannot write {}: {e}", path.display())))
            }
        }
    }

    /// Pin the deployment pointer and persist it immediately.
    pub fn record_deployment(&mut self, deployment_id: impl Into<String>, name: impl Into<String>) -> Result<()> {
        let mut d = HashMap::new();
        d.insert("id".to_string(), deployment_id.into());
        d.insert("name".to_string(), name.into());
        self.deployment = Some(d);
        self.save()
    }

    /// Drop the deployment pointer and persist it immediately.
    pub fn forget_deployment(&mut self) -> Result<()> {
        self.deployment = None;
        self.save()
    }
}

/// The nearest ancestor of `start` containing the project file, git-style.
pub fn find_project_root(start: Option<&Path>) -> Option<PathBuf> {
    let current = match start {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir().ok()?,
    };
    let current = current.canonicalize().ok()?;
    let mut dir: Option<PathBuf> = Some(current);
    while let Some(d) = dir {
        if d.join(PROJECT_FILE).is_file() {
            return Some(d);
        }
        dir = d.parent().map(|p| p.to_path_buf());
    }
    None
}

/// Read the project file in `root`.
pub fn load(root: &Path) -> Result<Project> {
    let path = root.join(PROJECT_FILE);
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| freepod(format!("cannot read {}: {e}", path.display())))?;
    let document: Value = serde_json::from_str(&raw)
        .map_err(|e| freepod(format!("{path:?} is not valid JSON: {e}")))?;
    let document = match document {
        Value::Object(_) => document,
        _ => return Err(freepod(format!("{path:?} must contain a JSON object"))),
    };

    let version = match document.get("version") {
        None => FORMAT_VERSION,
        Some(Value::Number(n)) => {
            let v = n.as_u64().unwrap_or(0);
            if v > FORMAT_VERSION {
                return Err(freepod(format!(
                    "{:?} declares format version {v}, which this client does not understand \
                     (it supports up to {FORMAT_VERSION}) — upgrade freepod",
                    path
                )));
            }
            v
        }
        Some(other) => {
            return Err(freepod(format!(
                "{:?} declares format version {other}, which this client does not understand \
                 (it supports up to {FORMAT_VERSION}) — upgrade freepod",
                path
            )))
        }
    };

    let env = match document.get("env") {
        Some(Value::String(s)) if !s.is_empty() => s.clone(),
        _ => {
            return Err(freepod(format!(
                "{:?} does not record which environment it belongs to",
                path
            )))
        }
    };

    let user_values = match document.get("user_values") {
        None => HashMap::new(),
        Some(Value::Object(obj)) => obj
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect(),
        Some(_) => {
            return Err(freepod(format!("{:?}: 'user_values' must be an object", path)))
        }
    };

    let deployment = match document.get("deployment") {
        None => None,
        Some(Value::Null) => None,
        Some(Value::Object(obj)) => {
            if obj.get("id").and_then(|v| v.as_str()).map(|s| !s.is_empty()).unwrap_or(false) {
                Some(
                    obj.iter()
                        .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                        .collect(),
                )
            } else {
                return Err(freepod(format!(
                    "{:?}: 'deployment' must be null or carry an 'id'",
                    path
                )));
            }
        }
        Some(_) => {
            return Err(freepod(format!(
                "{:?}: 'deployment' must be null or carry an 'id'",
                path
            )))
        }
    };

    Ok(Project {
        root: root.to_path_buf(),
        env,
        user_values,
        deployment,
        version,
    })
}

/// Find and load the project, refusing a directory that has none.
pub fn require_project(start: Option<&Path>) -> Result<Project> {
    let root = match find_project_root(start) {
        Some(r) => r,
        None => {
            let where_ = match start {
                Some(p) => p.to_path_buf(),
                None => std::env::current_dir().unwrap_or_default(),
            }
            .canonicalize()
            .unwrap_or_else(|_| std::env::current_dir().unwrap_or_default());
            return Err(usage(format!(
                "no {PROJECT_FILE} found in {} or any parent directory — \
                 this project is not initialized. Run `freepod init` to set it up.",
                where_.display()
            )));
        }
    };
    load(&root)
}
