//! `freepod var`: a deployment's runtime configuration.
//!
//! Mirrors `vars.py`. Values are strings on the wire. A sensitive var is
//! write-only — the platform returns it with no `value` at all — so an entry
//! carrying no value means "leave this one alone", which is what makes
//! `var list --json` output safe to submit back through `var set -f -`.

use std::collections::HashMap;
use std::io::Read;

use serde_json::{json, Map, Value};

use crate::api::{ApiResponse, ApiClient};
use crate::errors::{freepod, usage, Error, Result};
use crate::table::{format_time, render, value_str, BLANK};

/// The only phase that currently exists. Leaves room for build vars.
pub const PHASE: &str = "runtime";

/// Stands in for a value the platform will not return.
pub const HIDDEN: &str = "<hidden>";

const COLUMNS: [&str; 4] = ["KEY", "VALUE", "UPDATED", "BY"];

fn base(user_id: u64, deployment_id: &str) -> String {
    format!("/api/users/{user_id}/deployments/{deployment_id}/vars/{PHASE}")
}

/// The deployment's vars envelope: `{"vars": {...}, "pending": bool}`.
pub async fn read(api: &mut ApiClient, user_id: u64, deployment_id: &str) -> Result<Value> {
    let body = api.get_json(&base(user_id, deployment_id), None).await?;
    if !body.is_object() {
        return Err(freepod(format!("unexpected vars response: {body}")));
    }
    Ok(body)
}

/// Merge `entries` into the deployment's vars.
pub async fn write(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    entries: &Value,
) -> Result<Value> {
    let response = api
        .request(
            "PATCH",
            &base(user_id, deployment_id),
            None,
            Some(&json!({ "vars": entries })),
            None,
        )
        .await?;
    if !response.is_success() {
        return Err(write_error(&response));
    }
    response.decode()
}

/// Delete keys. Removing one that is not set is a no-op, not an error.
pub async fn remove(
    api: &mut ApiClient,
    user_id: u64,
    deployment_id: &str,
    keys: &[String],
) -> Result<()> {
    for key in keys {
        let response = api
            .delete(&format!("{}/{}", base(user_id, deployment_id), key))
            .await?;
        if !response.is_success() {
            return Err(write_error(&response));
        }
    }
    Ok(())
}

fn write_error(response: &ApiResponse) -> Error {
    let text = response.text();
    let detail = match serde_json::from_str::<Value>(&text) {
        Ok(Value::Object(obj)) => obj
            .get("detail")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        Ok(_) => String::new(),
        Err(_) => text.trim().chars().take(300).collect(),
    };
    if detail.is_empty() {
        freepod(format!("the platform refused the write: HTTP {}", response.status))
    } else {
        freepod(detail)
    }
}

// --------------------------------------------------------------------------
// Input
// --------------------------------------------------------------------------

/// `KEY=VALUE` pairs; a bare `KEY` is prompted for without echo.
///
/// Prompting is what keeps a secret out of the shell history, so a bare key
/// with nowhere to prompt is a usage error rather than an empty value.
pub fn parse_assignments(
    arguments: &[String],
    interactive: bool,
) -> Result<HashMap<String, String>> {
    let mut values: HashMap<String, String> = HashMap::new();
    for argument in arguments {
        let (key, value, has_separator) = match argument.find('=') {
            Some(idx) => (
                argument[..idx].trim().to_string(),
                argument[idx + 1..].to_string(),
                true,
            ),
            None => (argument.trim().to_string(), String::new(), false),
        };
        if key.is_empty() {
            return Err(usage(format!("'{argument}' is not a KEY=VALUE pair")));
        }
        if has_separator {
            values.insert(key, value);
            continue;
        }
        if !interactive {
            return Err(usage(format!(
                "no value given for {key}, and there is no terminal to prompt on.\n  \
                 Pass {key}=VALUE, or -f FILE, or pipe the wire shape into -f -."
            )));
        }
        let secret = crate::prompt::prompt_secret(&format!("Value for {key}"))?;
        values.insert(key, secret);
    }
    Ok(values)
}

/// Read vars from a file, or from stdin when `source` is `-`.
///
/// Accepts the platform's own wire shape (so `var list --json` round-trips)
/// or plain `KEY=VALUE` lines.
pub fn load_entries(source: &str) -> Result<Value> {
    let (text, origin) = if source == "-" {
        let mut text = String::new();
        std::io::stdin()
            .read_to_string(&mut text)
            .map_err(|e| freepod(format!("could not read standard input: {e}")))?;
        (text, "standard input".to_string())
    } else {
        let path = std::path::Path::new(source);
        if !path.is_file() {
            return Err(usage(format!("{source}: no such file")));
        }
        let text = std::fs::read_to_string(path)
            .map_err(|e| freepod(format!("cannot read {source}: {e}")))?;
        (text, source.to_string())
    };

    if text.trim_start().starts_with('{') {
        let document: Value = serde_json::from_str(&text)
            .map_err(|e| usage(format!("{origin}: not valid JSON ({e})")))?;
        entries_from_wire(&document, &origin)
    } else {
        let mut obj = Map::new();
        for (key, value) in entries_from_lines(&text, &origin)? {
            obj.insert(key, json!({ "value": value }));
        }
        Ok(Value::Object(obj))
    }
}

fn entries_from_wire(document: &Value, origin: &str) -> Result<Value> {
    let doc = match document.as_object() {
        Some(o) => o,
        None => return Err(usage(format!("{origin}: expected an object"))),
    };
    // Both the envelope and a bare map, because one is what `--json` prints
    // and the other is what a person writing the file by hand would produce.
    let vars_ = match doc.get("vars") {
        Some(v) => v,
        None => document,
    };
    let vars_ = match vars_.as_object() {
        Some(o) => o,
        None => return Err(usage(format!("{origin}: 'vars' is not an object"))),
    };

    let mut entries = Map::new();
    for (key, entry) in vars_ {
        match entry {
            Value::String(_) | Value::Null => {
                entries.insert(key.clone(), json!({ "value": entry }));
            }
            Value::Object(fields) => {
                // Only the two fields a write carries. `updated_at`/`updated_by`
                // come back on a read and are the platform's to set.
                let mut kept = Map::new();
                if let Some(v) = fields.get("value") {
                    kept.insert("value".to_string(), v.clone());
                }
                if let Some(s) = fields.get("sensitive") {
                    kept.insert("sensitive".to_string(), s.clone());
                }
                entries.insert(key.clone(), Value::Object(kept));
            }
            _ => {
                return Err(usage(format!(
                    "{origin}: {key} is neither a string nor an object"
                )))
            }
        }
    }
    Ok(Value::Object(entries))
}

fn entries_from_lines(text: &str, origin: &str) -> Result<Vec<(String, String)>> {
    let mut values: Vec<(String, String)> = Vec::new();
    for (index, line) in text.lines().enumerate() {
        let stripped = line.trim();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        let (key, value) = match stripped.find('=') {
            Some(idx) => (stripped[..idx].trim().to_string(), stripped[idx + 1..].to_string()),
            None => {
                return Err(usage(format!(
                    "{origin}:{}: expected KEY=VALUE, got '{line}'",
                    index + 1
                )))
            }
        };
        if key.is_empty() {
            return Err(usage(format!(
                "{origin}:{}: expected KEY=VALUE, got '{line}'",
                index + 1
            )));
        }
        values.push((key, value));
    }
    Ok(values)
}

/// Whether the deployment's template declares `key`, and so owns its
/// sensitivity.
pub fn schema_declares(deployment: &Value, key: &str) -> bool {
    let template = deployment
        .get("desired_template")
        .filter(|v| v.is_object())
        .unwrap_or(&Value::Null);
    let schema = template
        .get("values_schema_json")
        .filter(|v| v.is_object())
        .unwrap_or(&Value::Null);
    match schema.get("properties") {
        Some(Value::Object(properties)) => properties.contains_key(key),
        _ => false,
    }
}

/// Flag every entry sensitive, except where the schema already decides.
///
/// Returns the keys left alone, which the caller warns about.
pub fn mark_sensitive(entries: &mut Value, deployment: &Value) -> Vec<String> {
    let mut declared = Vec::new();
    if let Some(obj) = entries.as_object_mut() {
        for (key, entry) in obj.iter_mut() {
            if schema_declares(deployment, key) {
                declared.push(key.clone());
                continue;
            }
            if let Some(e) = entry.as_object_mut() {
                e.insert("sensitive".to_string(), Value::Bool(true));
            }
        }
    }
    declared
}

// --------------------------------------------------------------------------
// Output
// --------------------------------------------------------------------------

/// Who last wrote it, by email. The id is in `--json` and not here: it
/// identifies an account to a program, not to a person.
pub fn author(entry: &Value) -> String {
    let Some(writer) = entry.get("updated_by").and_then(|v| v.as_object()) else {
        return BLANK.to_string();
    };
    writer
        .get("email")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(String::from)
        .unwrap_or_else(|| BLANK.to_string())
}

/// One row per var, sorted by key, headers first.
pub fn rows(payload: &Value) -> Vec<Vec<String>> {
    let mut table: Vec<Vec<String>> = vec![COLUMNS.iter().map(|s| s.to_string()).collect()];
    if let Some(vars) = payload.get("vars").and_then(|v| v.as_object()) {
        let mut keys: Vec<&String> = vars.keys().collect();
        keys.sort();
        for key in keys {
            let entry = &vars[key];
            let value = match entry.get("value") {
                None => HIDDEN.to_string(),
                Some(v) => value_str(v),
            };
            table.push(vec![
                key.clone(),
                value,
                format_time(entry.get("updated_at").unwrap_or(&Value::Null)),
                author(entry),
            ]);
        }
    }
    table
}

/// The rendered table, or empty where the deployment has no vars.
pub fn render_table(payload: &Value) -> String {
    let body = rows(payload);
    if body.len() <= 1 {
        return String::new();
    }
    render(&body)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parse_assignments_splits_on_the_first_separator() {
        let values = parse_assignments(&["A=1".into(), "B=x=y".into()], false).unwrap();
        assert_eq!(values.get("A").map(String::as_str), Some("1"));
        assert_eq!(values.get("B").map(String::as_str), Some("x=y"));
    }

    #[test]
    fn parse_assignments_rejects_an_empty_key() {
        assert!(matches!(
            parse_assignments(&["=v".into()], false),
            Err(Error::Usage(_))
        ));
    }

    #[test]
    fn parse_assignments_bare_key_needs_a_terminal() {
        assert!(matches!(
            parse_assignments(&["SECRET".into()], false),
            Err(Error::Usage(_))
        ));
    }

    #[test]
    fn load_entries_reads_the_wire_shape() {
        let value = load_entries_from_text(
            r#"{"vars": {"A": "1", "B": {"value": "2", "sensitive": true, "updated_at": "x"}}}"#,
        )
        .unwrap();
        let obj = value.as_object().unwrap();
        assert_eq!(obj.get("A"), Some(&json!({ "value": "1" })));
        assert_eq!(
            obj.get("B"),
            Some(&json!({ "value": "2", "sensitive": true }))
        );
    }

    #[test]
    fn load_entries_reads_key_value_lines() {
        let value = load_entries_from_text("# comment\nA=1\n\nB=two words\n").unwrap();
        let obj = value.as_object().unwrap();
        assert_eq!(obj.get("A"), Some(&json!({ "value": "1" })));
        assert_eq!(obj.get("B"), Some(&json!({ "value": "two words" })));
    }

    #[test]
    fn load_entries_rejects_a_bad_line() {
        assert!(matches!(
            load_entries_from_text("A=1\nnot a pair\n"),
            Err(Error::Usage(_))
        ));
    }

    /// `load_entries` reads files or stdin; the tests feed it text directly.
    fn load_entries_from_text(text: &str) -> Result<Value> {
        let stripped = text.trim_start();
        if stripped.starts_with('{') {
            let document: Value = serde_json::from_str(text)
                .map_err(|e| usage(format!("test: not valid JSON ({e})")))?;
            entries_from_wire(&document, "test")
        } else {
            let mut obj = Map::new();
            for (key, value) in entries_from_lines(text, "test")? {
                obj.insert(key, json!({ "value": value }));
            }
            Ok(Value::Object(obj))
        }
    }

    #[test]
    fn schema_declares_reads_the_desired_template() {
        let deployment = json!({
            "desired_template": {
                "values_schema_json": { "properties": { "hostname": {} } }
            }
        });
        assert!(schema_declares(&deployment, "hostname"));
        assert!(!schema_declares(&deployment, "other"));
        assert!(!schema_declares(&json!({}), "hostname"));
        assert!(!schema_declares(&json!({ "desired_template": null }), "hostname"));
    }

    #[test]
    fn mark_sensitive_skips_schema_owned_keys() {
        let deployment = json!({
            "desired_template": {
                "values_schema_json": { "properties": { "hostname": {} } }
            }
        });
        let mut entries = json!({ "hostname": { "value": "a" }, "SECRET": { "value": "b" } });
        let declared = mark_sensitive(&mut entries, &deployment);
        assert_eq!(declared, vec!["hostname"]);
        assert_eq!(
            entries.get("SECRET").and_then(|v| v.get("sensitive")),
            Some(&json!(true))
        );
        assert!(entries.get("hostname").and_then(|v| v.get("sensitive")).is_none());
    }

    #[test]
    fn rows_hide_sensitive_values() {
        let payload = json!({
            "vars": {
                "A": { "value": "1", "updated_by": { "email": "a@x" } },
                "B": { "sensitive": true }
            }
        });
        let table = rows(&payload);
        assert_eq!(table[1][1], "1");
        assert_eq!(table[2][1], HIDDEN);
        assert_eq!(table[1][3], "a@x");
    }
}
