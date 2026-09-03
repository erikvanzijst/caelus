//! The error hierarchy and the exit codes.
//!
//! Every other module raises from this one. Each error carries the exit code
//! its class maps onto; the base `Freepod` variant is the "unexpected error"
//! row. Mirrors the Python package's `__init__.py`.

use std::fmt;

pub const EXIT_ERROR: i32 = 1;
pub const EXIT_USAGE: i32 = 2;
pub const EXIT_NOT_AUTHENTICATED: i32 = 3;
pub const EXIT_BUILD_FAILED: i32 = 4;
pub const EXIT_ROLLOUT_FAILED: i32 = 5;

/// Anything that should end the run with a readable message.
#[derive(Debug)]
pub enum Error {
    /// The "unexpected error" row — exit 1.
    Freepod(String),
    /// The command was invoked wrongly. Nothing was attempted — exit 2.
    Usage(String),
    /// No usable credential, or one the platform will not accept — exit 3.
    Authentication(String),
    /// Authenticated, but not permitted to act on the resource — exit 1.
    Permission(String),
    /// The build reached a non-successful terminal status — exit 4.
    BuildFailed(String),
    /// The rollout failed, or waiting for it timed out — exit 5.
    RolloutFailed(String),
    /// The edge presented a host key other than the one the platform
    /// publishes. A refused connection, not a guess: the mismatch is what
    /// `ssh` reported, so unlike a uniform authentication refusal this one
    /// names its cause. It is a general error rather than an authentication
    /// failure, because re-authenticating cannot fix a host that is answering
    /// where the edge should be — exit 1.
    HostKeyMismatch(String),
}

impl Error {
    pub fn exit_code(&self) -> i32 {
        match self {
            Error::Freepod(_) | Error::Permission(_) => EXIT_ERROR,
            Error::Usage(_) => EXIT_USAGE,
            Error::Authentication(_) => EXIT_NOT_AUTHENTICATED,
            Error::BuildFailed(_) => EXIT_BUILD_FAILED,
            Error::RolloutFailed(_) => EXIT_ROLLOUT_FAILED,
            Error::HostKeyMismatch(_) => EXIT_ERROR,
        }
    }

    pub fn message(&self) -> &str {
        match self {
            Error::Freepod(m)
            | Error::Usage(m)
            | Error::Authentication(m)
            | Error::Permission(m)
            | Error::BuildFailed(m)
            | Error::RolloutFailed(m)
            | Error::HostKeyMismatch(m) => m,
        }
    }

    /// Return a copy of this error in the *same* variant with `suffix`
    /// appended on a new line. Preserves the exit code, which is what lets a
    /// failed rollout re-raised from `var set` still exit 5.
    pub fn with_suffix(&self, suffix: &str) -> Error {
        let msg = format!("{}\n{}", self.message(), suffix);
        match self {
            Error::Freepod(_) => Error::Freepod(msg),
            Error::Usage(_) => Error::Usage(msg),
            Error::Authentication(_) => Error::Authentication(msg),
            Error::Permission(_) => Error::Permission(msg),
            Error::BuildFailed(_) => Error::BuildFailed(msg),
            Error::RolloutFailed(_) => Error::RolloutFailed(msg),
            Error::HostKeyMismatch(_) => Error::HostKeyMismatch(msg),
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message())
    }
}

impl std::error::Error for Error {}

/// Convenience constructors.
pub fn freepod(msg: impl Into<String>) -> Error {
    Error::Freepod(msg.into())
}
pub fn usage(msg: impl Into<String>) -> Error {
    Error::Usage(msg.into())
}
pub fn authentication(msg: impl Into<String>) -> Error {
    Error::Authentication(msg.into())
}
pub fn permission(msg: impl Into<String>) -> Error {
    Error::Permission(msg.into())
}
pub fn build_failed(msg: impl Into<String>) -> Error {
    Error::BuildFailed(msg.into())
}
pub fn rollout_failed(msg: impl Into<String>) -> Error {
    Error::RolloutFailed(msg.into())
}
pub fn host_key_mismatch(msg: impl Into<String>) -> Error {
    Error::HostKeyMismatch(msg.into())
}

/// The result type used throughout the client.
pub type Result<T> = std::result::Result<T, Error>;
