use crate::{project, report, workflow};
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    time::Instant,
};
use wraith_core::{
    cancellation::Cancellation,
    comparison::{self, ComparisonReport, Severity},
    config,
    error::{self, Error},
    model::RunSnapshot,
    runner, snapshot,
};

pub struct Options {
    pub samples: u32,
    pub jobs: u32,
    pub artifacts: Option<PathBuf>,
    pub summary: Option<PathBuf>,
    pub json: bool,
}

fn status(exit: u8) -> &'static str {
    match exit {
        0 => "Passed",
        1 => "Failed",
        3 => "Inconclusive",
        _ => "Execution error",
    }
}

fn code(value: &impl serde::Serialize) -> String {
    let text = serde_json::to_string_pretty(value).unwrap_or_default();
    let short: String = text.chars().take(600).collect();
    format!(
        "<pre>{}{}</pre>\n\n",
        report::escape(&short),
        if text.chars().count() > 600 {
            "… (see artifacts)"
        } else {
            ""
        }
    )
}

fn label(value: &str) -> String {
    let short: String = value.replace(['\n', '\r'], " ").chars().take(160).collect();
    report::escape(&short)
        .chars()
        .fold(String::new(), |mut text, ch| {
            if "\\`*_[]()!|".contains(ch) {
                text.push('\\');
            }
            text.push(ch);
            text
        })
}

fn markdown(
    baseline: &RunSnapshot,
    candidate: Option<&RunSnapshot>,
    comparison: Option<&ComparisonReport>,
    exit: u8,
) -> String {
    let status = status(exit);
    let count = |run: &RunSnapshot| {
        format!(
            "{}/{} observations pass",
            run.scenarios.iter().filter(|s| s.passed).count(),
            run.scenarios.len()
        )
    };
    let mut text = format!(
        "## Wraith: {status}\n\nBaseline: {}. Candidate: {}.\n\n",
        count(baseline),
        candidate
            .map(count)
            .unwrap_or_else(|| "not executed; fix the baseline first".into())
    );
    if let Some(comparison) = comparison {
        let failures: Vec<_> = comparison
            .changes
            .iter()
            .filter(|c| c.severity == Severity::Failure)
            .collect();
        if exit == 0 {
            text.push_str("No new configured regressions.\n\n");
        }
        for change in failures.iter().take(20) {
            text.push_str(&format!(
                "### <code>{}</code>\n\n{}\n\nBaseline\n\n{}\n\nCandidate\n\n{}\n\n",
                label(&change.scenario_id),
                code(&change.message),
                code(&change.baseline),
                code(&change.candidate)
            ));
        }
        if failures.len() > 20 {
            text.push_str("More failures are retained in the HTML/JSON artifacts.\n\n");
        }
        for threshold in comparison.thresholds.iter().filter(|t| !t.passed) {
            text.push_str(&format!(
                "Failed threshold\n\n{}\n\n",
                code(&threshold.message)
            ));
        }
        if comparison.inconclusive {
            text.push_str(
                "More samples are required. Inconclusive results block this check (exit 3).\n\n",
            );
        }
        let changed = comparison
            .changes
            .iter()
            .filter(|c| c.severity != Severity::Failure)
            .count();
        text.push_str(&format!(
            "{changed} informational or warning entries are available in the full report.\n\n"
        ));
    } else {
        for scenario in baseline.scenarios.iter().filter(|s| !s.passed).take(20) {
            text.push_str(&format!(
                "Baseline failure: <code>{}</code>\n\n",
                label(&scenario.scenario.id)
            ));
            if let Some(error) = &scenario.run.error {
                text.push_str(&code(&error.message));
            }
            for check in scenario.evaluations.iter().filter(|e| !e.passed).take(5) {
                text.push_str(&code(&check.message));
            }
            text.push_str("\n\n");
        }
    }
    text.push_str("Download the Wraith artifacts for report.html and full JSON evidence. These results cover the configured scenarios; they do not establish overall agent quality.\n");
    text
}

pub async fn execute(
    candidate_config: &Path,
    base_config: &Path,
    options: Options,
    cancellation: Cancellation,
) -> Result<u8, Error> {
    let (policy, base) = config::load(base_config)?;
    let base =
        fs::canonicalize(&base).map_err(|e| error::io("resolve base directory", &base, e))?;
    let candidate = fs::canonicalize(project::directory(candidate_config)).map_err(|e| {
        error::io(
            "resolve candidate directory",
            project::directory(candidate_config),
            e,
        )
    })?;
    for directory in [&base, &candidate] {
        if project::load(directory)?.is_some_and(|p| p.mode == "live") {
            return Err(Error::Config(
                "ci check is offline-only; no live agent was executed".into(),
            ));
        }
    }
    if options
        .summary
        .as_ref()
        .is_some_and(|p| p.file_name().is_none())
    {
        return Err(Error::Config(
            "--summary needs a file path; omit it outside CI".into(),
        ));
    }
    let output = options.artifacts.clone().unwrap_or_else(|| {
        candidate.join(format!(
            ".wraith/ci/{}-{}",
            runner::unix_ms(),
            std::process::id()
        ))
    });
    if let Some(parent) = output.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)
            .map_err(|e| error::io("create CI artifact parent", parent, e))?;
    }
    fs::create_dir(&output).map_err(|e| {
        error::io(
            "create fresh CI artifact directory (never overwrite prior evidence)",
            &output,
            e,
        )
    })?;
    let output = fs::canonicalize(&output)
        .map_err(|e| error::io("resolve artifact directory", &output, e))?;
    if let Some(path) = &options.summary {
        let resolved = if path.exists() {
            fs::canonicalize(path)
        } else {
            fs::canonicalize(
                path.parent()
                    .filter(|p| !p.as_os_str().is_empty())
                    .unwrap_or(Path::new(".")),
            )
            .map(|parent| parent.join(path.file_name().unwrap_or_default()))
        }
        .map_err(|e| error::io("resolve summary destination", path, e))?;
        if resolved.is_dir() {
            return Err(Error::Config(
                "--summary needs a file, not a directory".into(),
            ));
        }
        if resolved.starts_with(&output) {
            return Err(Error::Config("--summary must be outside the artifact directory; summary.md is already saved there".into()));
        }
    }
    workflow::atomic_json(&output.join("policy.json"), &policy)?;
    let settings = runner::RunOptions {
        samples: options.samples,
        jobs: options.jobs,
        cancellation: cancellation.clone(),
        request_budget: None,
    };
    let started = Instant::now();
    let baseline = runner::run_with_options(&policy, &base, None, &settings).await?;
    if cancellation.is_cancelled() {
        return Err(Error::Cancelled);
    }
    snapshot::save(&output.join("baseline.json"), &baseline)?;
    let mut exit = workflow::run_exit(&baseline);
    let mut after = None;
    let mut comparison = None;
    if exit == 0 {
        let candidate_run = runner::run_with_options(&policy, &candidate, None, &settings).await?;
        if cancellation.is_cancelled() {
            return Err(Error::Cancelled);
        }
        snapshot::save(&output.join("candidate.json"), &candidate_run)?;
        let decision = comparison::compare_with_policy(&baseline, &candidate_run, Some(&policy))?;
        exit = workflow::comparison_exit(&decision);
        workflow::atomic_json(&output.join("comparison.json"), &decision)?;
        after = Some(candidate_run);
        comparison = Some(decision);
    }
    report::save(
        &output.join("report.html"),
        after.as_ref().unwrap_or(&baseline),
        after.as_ref().map(|_| &baseline),
        comparison.as_ref(),
        None,
    )?;
    let summary = markdown(&baseline, after.as_ref(), comparison.as_ref(), exit);
    fs::write(output.join("summary.md"), &summary)
        .map_err(|e| error::io("write summary", &output, e))?;
    if let Some(path) = &options.summary {
        let mut file = fs::OpenOptions::new()
            .append(true)
            .create(true)
            .open(path)
            .map_err(|e| error::io("append CI summary", path, e))?;
        file.write_all(summary.as_bytes())
            .map_err(|e| error::io("write CI summary", path, e))?;
    }
    let result: Value = json!({"schemaVersion":1,"exitCode":exit,"baselinePassed":workflow::run_exit(&baseline)==0,
        "candidateExecuted":after.is_some(),"jobs":options.jobs,"samples":options.samples,
        "wallSeconds":started.elapsed().as_secs_f64(),"artifacts":output,
        "baselineConfig":base_config,"candidateDirectory":candidate,
        "baseGit":{"commit":workflow::git(&base,&["rev-parse","HEAD"]),"dirty":workflow::git(&base,&["status","--porcelain"]).is_some_and(|s|!s.is_empty())},
        "candidateGit":{"commit":workflow::git(&candidate,&["rev-parse","HEAD"]),"dirty":workflow::git(&candidate,&["status","--porcelain"]).is_some_and(|s|!s.is_empty())},
        "comparison":comparison});
    workflow::atomic_json(&output.join("ci.json"), &result)?;
    if options.json {
        println!(
            "{}",
            serde_json::to_string_pretty(&result).map_err(|e| Error::Artifact(e.to_string()))?
        );
    } else {
        println!("Wraith CI: {} (exit {exit}).", status(exit));
        if after.is_none() {
            println!("Baseline checks failed; candidate was not executed.");
        }
        if let Some(decision) = &comparison {
            for change in decision
                .changes
                .iter()
                .filter(|c| c.severity == Severity::Failure)
                .take(20)
            {
                println!("{}: {}", change.scenario_id, change.message);
            }
        }
        println!(
            "Summary: {}\nReport: {}",
            output.join("summary.md").display(),
            output.join("report.html").display()
        );
    }
    Ok(exit)
}
