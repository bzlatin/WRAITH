use std::path::Path;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error(
        "WRAITH run interrupted. Agent processes were terminated; no complete snapshot was saved."
    )]
    Cancelled,
    #[error("Invalid WRAITH configuration: {0}")]
    Config(String),
    #[error("WRAITH artifact error: {0}")]
    Artifact(String),
    #[error("Cannot compare these runs: {0}")]
    Comparison(String),
    #[error("Could not {action} {path}: {source}")]
    Io {
        action: &'static str,
        path: String,
        source: std::io::Error,
    },
}

pub fn io(action: &'static str, path: &Path, source: std::io::Error) -> Error {
    Error::Io {
        action,
        path: path.display().to_string(),
        source,
    }
}
