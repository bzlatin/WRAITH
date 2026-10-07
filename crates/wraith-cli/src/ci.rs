use crate::project;
use clap::Subcommand;
use std::{fs, path::Path};
use wraith_core::{config, error::Error};

#[derive(Subcommand)]
pub enum Commands {
    /// Write .github/workflows/wraith.yml; never overwrite an existing workflow.
    Init {
        /// Pin a published Wraith binary version.
        #[arg(long, default_value=env!("CARGO_PKG_VERSION"))]
        version: String,
    },
}

pub fn execute(path: &Path, command: Commands) -> Result<(), Error> {
    let Commands::Init { version } = command;
    if !version
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-')
        || version.is_empty()
    {
        return Err(Error::Config(
            "Version must be a release version without path separators".into(),
        ));
    }
    config::load(path)?;
    let directory = project::directory(path);
    if project::load(directory)?.is_some_and(|p| p.mode == "live") {
        return Err(Error::Config("Generated CI is offline-only. Use an offline config; live CI requires a deliberate credential and request-budget policy.".into()));
    }
    let root = std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .current_dir(directory)
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .ok_or_else(|| Error::Config("Run ci init inside a Git repository".into()))?;
    // Canonicalize both sides: Windows canonical paths may carry a \\?\ prefix.
    let root = fs::canonicalize(root.trim()).map_err(|e| Error::Config(e.to_string()))?;
    let absolute = fs::canonicalize(path).map_err(|e| Error::Config(e.to_string()))?;
    let relative = absolute
        .strip_prefix(&root)
        .map_err(|_| Error::Config("Config must be inside the repository".into()))?
        .to_string_lossy()
        .replace('\\', "/");
    if relative.contains('\n') || relative.contains('\r') {
        return Err(Error::Config(
            "Config filename cannot contain newlines".into(),
        ));
    }
    let yaml = include_str!("../../../templates/github-workflow.yml")
        .replace("__VERSION__", &version)
        .replace(
            "__CONFIG_JSON__",
            &serde_json::to_string(&relative).map_err(|e| Error::Config(e.to_string()))?,
        );
    let target = root.join(".github/workflows/wraith.yml");
    project::write_new(&target, yaml.as_bytes())?;
    println!(
        "Created {}.\nReview the dependency-install step for your project. Commit the config, adapters, and workflow.\nThe installer requires published Wraith v{version} assets; an unpublished version cannot be downloaded.\nThe workflow evaluates the exact PR base and candidate with an offline suite and retains HTML/JSON evidence.",
        target.display()
    );
    Ok(())
}
