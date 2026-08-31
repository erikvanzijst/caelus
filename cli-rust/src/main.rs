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
mod table;
mod tos;
mod values;
mod vars;

fn main() {
    std::process::exit(cli::run());
}
