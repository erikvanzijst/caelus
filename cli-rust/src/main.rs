//! The `freepod` command-line client (Rust port).
//!
//! Stream discipline: results go to stdout, everything else to stderr, so a
//! piped stdout carries only the result.

mod api;
mod archive;
mod auth;
mod build;
mod cli;
mod config;
mod database;
mod delete;
mod deploy;
mod errors;
mod history;
mod keys;
mod logs;
mod project;
mod prompt;
mod releases;
mod skill;
mod ssh;
mod table;
mod tos;
mod values;
mod vars;

fn main() {
    std::process::exit(cli::run());
}

#[cfg(test)]
pub mod testutil {
    /// Serialize every test that mutates the process-wide environment
    /// (`HOME`, `XDG_CONFIG_HOME`, `PATH`): the environment is shared by all
    /// test threads in the binary, so two of them repointing it at once would
    /// read each other's directories.
    pub static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
}
