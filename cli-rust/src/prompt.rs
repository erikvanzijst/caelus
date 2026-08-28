//! Interactive prompts and confirmations, written to stderr.
//!
//! Mirrors the `click.prompt` / `click.confirm` calls the Python client made
//! with `err=True`: diagnostics and questions go to stderr so a piped stdout
//! carries only the result.

use dialoguer::console::Term;
use dialoguer::{Confirm, Input, Password};

use crate::errors::Result;

fn term() -> Term {
    Term::stderr()
}

/// Read a line of input, optionally showing a default.
pub fn prompt_with_default(prompt: &str, default: Option<&str>) -> Result<String> {
    let mut input = Input::new().with_prompt(prompt);
    if let Some(d) = default {
        input = input.default(d.to_string());
    }
    input
        .interact_on(&term())
        .map_err(|e| crate::errors::usage(format!("could not read input: {e}")))
}

/// Read a value without echoing it (a bare `KEY` in `var set`).
pub fn prompt_secret(prompt: &str) -> Result<String> {
    Password::new()
        .with_prompt(prompt)
        .interact_on(&term())
        .map_err(|e| crate::errors::usage(format!("could not read input: {e}")))
}

/// A yes/no question. `default` is the answer when the user just presses enter.
pub fn confirm(question: &str, default: bool) -> Result<bool> {
    Confirm::new()
        .with_prompt(question)
        .default(default)
        .interact_on(&term())
        .map_err(|e| crate::errors::usage(format!("could not read input: {e}")))
}
