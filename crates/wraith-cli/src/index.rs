use crate::{Output, report};
use clap::Subcommand;
use std::{
    fs::{self, File},
    io::{BufReader, Write},
    path::{Path, PathBuf},
};
use wraith_core::{
    cancellation::Cancellation,
    error::{self, Error},
    index_audit::{self, Audit},
};

#[derive(Subcommand)]
pub enum Commands {
    /// Check sorted, versioned JSONL exports; no database access or model calls.
    Check {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        inventory: PathBuf,
        /// Save a complete JSON report to a new file (never overwrites).
        #[arg(long)]
        json: Option<PathBuf>,
        /// Save a self-contained HTML report to a new file (never overwrites).
        #[arg(long)]
        html: Option<PathBuf>,
        #[arg(long, value_enum, default_value_t=Output::Human)]
        output: Output,
    },
}

pub async fn execute(command: Commands, cancellation: Cancellation) -> Result<u8, Error> {
    let Commands::Check {
        manifest,
        inventory,
        json,
        html,
        output,
    } = command;
    let token = cancellation.clone();
    let audit = tokio::task::spawn_blocking(move || {
        for path in [&manifest, &inventory] {
            if !fs::metadata(path)
                .map_err(|e| error::io("inspect index input", path, e))?
                .is_file()
            {
                return Err(Error::Artifact("Index inputs must be regular files".into()));
            }
        }
        let manifest_file =
            File::open(&manifest).map_err(|e| error::io("open manifest", &manifest, e))?;
        let inventory_file =
            File::open(&inventory).map_err(|e| error::io("open inventory", &inventory, e))?;
        index_audit::check(
            BufReader::new(manifest_file),
            BufReader::new(inventory_file),
            &token,
        )
    })
    .await
    .map_err(|_| Error::Artifact("Index audit worker failed".into()))??;
    if cancellation.is_cancelled() {
        return Err(Error::Cancelled);
    }
    let serialized =
        serde_json::to_string_pretty(&audit).map_err(|e| Error::Artifact(e.to_string()))?;
    if let Some(path) = json {
        save_new(&path, &(serialized.clone() + "\n"))?;
    }
    if let Some(path) = html {
        save_new(&path, &render(&audit))?;
    }
    match output {
        Output::Json => println!("{serialized}"),
        Output::Human => {
            println!(
                "Index check: {:?} — {} passed, {} failed, {} pending, {} unknown",
                audit.status,
                audit.summary.passed,
                audit.summary.failed,
                audit.summary.pending,
                audit.summary.unknown
            );
            for issue in &audit.coverage_issues {
                println!("UNKNOWN: {issue}");
            }
            for f in audit.findings.iter().take(20) {
                println!(
                    "{:?} {}/{}: {} (missing {}, unexpected {}, stale {})\n  {}",
                    f.status,
                    f.tenant,
                    f.document_id,
                    f.reason,
                    f.missing_count,
                    f.unexpected_count,
                    f.stale_count,
                    f.next_action
                );
            }
            if audit.findings.len() > 20 || audit.omitted_findings > 0 {
                println!(
                    "Console details limited to 20 documents; use --json or --html for the bounded report."
                );
            }
        }
    }
    Ok(audit.exit_code())
}

fn save_new(path: &Path, contents: &str) -> Result<(), Error> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|e| error::io("create report directory", parent, e))?;
    let mut file =
        tempfile::NamedTempFile::new_in(parent).map_err(|e| error::io("create report", path, e))?;
    file.write_all(contents.as_bytes())
        .and_then(|()| file.as_file().sync_all())
        .map_err(|e| error::io("write report", path, e))?;
    file.persist_noclobber(path)
        .map_err(|e| error::io("save new report (choose an unused path)", path, e.error))?;
    Ok(())
}

fn render(audit: &Audit) -> String {
    let escape = report::escape;
    let mut body = format!(
        "<h1>Index check: {:?}</h1><p>Scope: <code>{}</code> · generation: <code>{}</code></p><p>{} passed · {} failed · {} pending · {} unknown documents</p><p>Metadata reconciliation only. This does not measure answer quality, retrieval exposure, or physical erasure.</p>",
        audit.status,
        escape(&audit.manifest.scope),
        escape(&audit.manifest.generation),
        audit.summary.passed,
        audit.summary.failed,
        audit.summary.pending,
        audit.summary.unknown
    );
    for issue in &audit.coverage_issues {
        body += &format!("<p><strong>Unknown:</strong> {}</p>", escape(issue));
    }
    for f in &audit.findings {
        body += &format!(
            "<section><h2>{:?}: {}/{}</h2><p>{}</p><p>Expected revision: <code>{}</code> · observed chunks: {}</p><p>Missing: {} · unexpected: {} · stale: {}</p><p><strong>Next action:</strong> {}</p><details><summary>Chunk evidence and ingestion job</summary><pre>{}</pre></details></section>",
            f.status,
            escape(&f.tenant),
            escape(&f.document_id),
            escape(&f.reason),
            escape(f.expected_revision.as_deref().unwrap_or("unavailable")),
            f.observed_chunks,
            f.missing_count,
            f.unexpected_count,
            f.stale_count,
            escape(&f.next_action),
            escape(&serde_json::to_string_pretty(f).expect("serializable finding"))
        );
    }
    body += &format!(
        "<p>Report includes at most 1,000 document findings and 20 chunk examples per category. Omitted document findings: {}. Totals cover every validated row.</p>",
        audit.omitted_findings
    );
    report::shell("Wraith index check", &body)
}
