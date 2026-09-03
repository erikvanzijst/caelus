//! Shared rendering for the client's listing commands.
//!
//! A leaf module: `history` and `releases` both draw the same kind of table.
//! Mirrors `table.py`.

use chrono::{DateTime, Duration, TimeZone, Utc};
use serde_json::Value;

/// Digest characters kept when abbreviating an image reference.
pub const SHORT_DIGEST: usize = 12;

/// Column separator. Two spaces.
pub const GAP: &str = "  ";

/// Shown where the platform has no value yet.
pub const BLANK: &str = "-";

/// A JSON value the way Python's `str()` reads it: a string bare, a number as
/// its digits, and a missing/null value as the blank.
pub fn value_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Null => BLANK.to_string(),
        other => other.to_string(),
    }
}

/// One of the platform's timestamps, as an aware UTC datetime.
///
/// The API serializes naive datetimes that are UTC by construction, so a
/// missing offset is read as UTC rather than as local time.
pub fn parse_time(value: &Value) -> Option<DateTime<Utc>> {
    let text = value.as_str()?;
    if text.is_empty() {
        return None;
    }
    let text = if let Some(stripped) = text.strip_suffix('Z') {
        format!("{stripped}+00:00")
    } else {
        text.to_string()
    };
    match DateTime::parse_from_rfc3339(&text) {
        Ok(dt) => Some(dt.with_timezone(&Utc)),
        Err(_) => {
            // Naive: read as UTC.
            if let Ok(naive) = chrono::NaiveDateTime::parse_from_str(&text, "%Y-%m-%dT%H:%M:%S%.f") {
                Some(Utc.from_utc_datetime(&naive))
            } else {
                None
            }
        }
    }
}

/// A timestamp in the reader's own timezone, to the minute.
pub fn format_time(value: &Value) -> String {
    match parse_time(value) {
        None => match value.as_str() {
            Some(s) if !s.is_empty() => s.to_string(),
            _ => BLANK.to_string(),
        },
        Some(stamp) => {
            let local = chrono::Local.from_utc_datetime(&stamp.naive_utc());
            local.format("%Y-%m-%d %H:%M").to_string()
        }
    }
}

/// `45s`, `3m 12s`, `1h 4m` — two units at most, largest first.
pub fn format_duration(delta: Option<Duration>) -> String {
    let Some(delta) = delta else {
        return BLANK.to_string();
    };
    let seconds = delta.num_seconds();
    if seconds < 0 || seconds < 60 {
        if seconds < 0 {
            return BLANK.to_string();
        }
        return format!("{seconds}s");
    }
    let minutes = seconds / 60;
    let seconds = seconds % 60;
    if minutes < 60 {
        return format!("{minutes}m {seconds}s");
    }
    let hours = minutes / 60;
    let minutes = minutes % 60;
    format!("{hours}h {minutes}m")
}

/// How long the work ran, or has been running.
///
/// Measured from when work *started*, never from when the record was created.
pub fn elapsed(
    started: &Value,
    finished: &Value,
    now: Option<DateTime<Utc>>,
) -> Option<Duration> {
    let begin = parse_time(started)?;
    let end = parse_time(finished);
    match end {
        None => Some((now.unwrap_or_else(Utc::now)) - begin),
        Some(e) => Some(e - begin),
    }
}

/// Shorten a digest reference to its first twelve characters.
pub fn abbreviate(image: &Value, full: bool) -> String {
    let Some(image) = image.as_str() else {
        return BLANK.to_string();
    };
    if image.is_empty() {
        return BLANK.to_string();
    }
    if full {
        return image.to_string();
    }
    match image.rfind("sha256:") {
        Some(idx) => {
            let digest = &image[idx + "sha256:".len()..];
            if digest.len() > SHORT_DIGEST {
                format!("{}…", &image[..idx + "sha256:".len() + SHORT_DIGEST])
            } else {
                image.to_string()
            }
        }
        None => image.to_string(),
    }
}

/// Character count, matching Python's `len` on a `str` (not byte length).
fn char_len(s: &str) -> usize {
    s.chars().count()
}

/// Left-pad-free `ljust`: pad a cell on the right to `width` characters.
fn ljust(s: &str, width: usize) -> String {
    let len = char_len(s);
    if len >= width {
        s.to_string()
    } else {
        format!("{s}{}", " ".repeat(width - len))
    }
}

/// Left-aligned columns, sized to their contents, with no trailing space.
pub fn render(table: &[Vec<String>]) -> String {
    if table.is_empty() {
        return String::new();
    }
    let columns = table[0].len();
    let widths: Vec<usize> = (0..columns)
        .map(|c| table.iter().map(|row| char_len(&row[c])).max().unwrap_or(0))
        .collect();
    table
        .iter()
        .map(|row| {
            let joined: Vec<String> = row
                .iter()
                .zip(widths.iter())
                .map(|(cell, w)| ljust(cell, *w))
                .collect();
            joined.join(GAP).trim_end().to_string()
        })
        .collect::<Vec<_>>()
        .join("\n")
}
