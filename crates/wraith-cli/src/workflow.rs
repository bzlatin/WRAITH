use crate::{project, render, report};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};
use wraith_core::{
    cancellation::Cancellation,
    comparison, config,
    error::{self, Error},
    model::RunSnapshot,
    runner, snapshot,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Record {
    pub version: u32,
    pub id: String,
    pub kind: String,
    pub baseline_id: Option<String>,
    pub created_at_unix_ms: u64,
    pub samples: u32,
    pub mode: String,
    pub model: Option<String>,
    pub agent_command: String,
    pub git_commit: Option<String>,
    pub git_dirty: bool,
    pub outcome: String,
    pub budget_id: Option<String>,
}

fn git(directory: &Path, args: &[&str]) -> Option<String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(directory)
        .output()
        .ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

pub fn atomic_json(path: &Path, value: &impl Serialize) -> Result<(), Error> {
    use std::io::Write;
    let parent = path
        .parent()
        .ok_or_else(|| Error::Artifact("Artifact path needs a parent".into()))?;
    fs::create_dir_all(parent).map_err(|e| error::io("create artifact directory", parent, e))?;
    let mut file = tempfile::NamedTempFile::new_in(parent)
        .map_err(|e| error::io("create artifact", path, e))?;
    serde_json::to_writer_pretty(&mut file, value).map_err(|e| Error::Artifact(e.to_string()))?;
    file.write_all(b"\n")
        .map_err(|e| error::io("write artifact", path, e))?;
    file.as_file()
        .sync_all()
        .map_err(|e| error::io("flush artifact", path, e))?;
    file.persist(path)
        .map_err(|e| error::io("save artifact", path, e.error))?;
    Ok(())
}

pub fn history_path(directory: &Path, id: &str) -> Result<PathBuf, Error> {
    if id.is_empty() || !id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        return Err(Error::Artifact("Invalid history identity".into()));
    }
    Ok(directory.join(".wraith/history").join(id))
}

pub fn load_record(path: &Path) -> Result<Record, Error> {
    let record: Record = serde_json::from_slice(
        &fs::read(path).map_err(|e| error::io("read workflow record", path, e))?,
    )
    .map_err(|e| Error::Artifact(e.to_string()))?;
    if record.version != 1
        || !["baseline", "check"].contains(&record.kind.as_str())
        || !["offline", "live"].contains(&record.mode.as_str())
    {
        return Err(Error::Artifact("Unsupported workflow record".into()));
    }
    history_path(Path::new("."), &record.id)?;
    if let Some(id) = &record.baseline_id {
        history_path(Path::new("."), id)?;
    }
    if let Some(id) = &record.budget_id {
        history_path(Path::new("."), id)?;
    }
    Ok(record)
}

pub fn history(directory: &Path) -> Result<Vec<Record>, Error> {
    let path = directory.join(".wraith/history");
    if !path.exists() {
        return Ok(vec![]);
    }
    let mut records = Vec::new();
    for entry in fs::read_dir(&path).map_err(|e| error::io("read history", &path, e))? {
        let entry = entry.map_err(|e| error::io("read history entry", &path, e))?;
        let record = entry.path().join("record.json");
        if record.is_file() {
            records.push(load_record(&record)?);
        }
    }
    records.sort_by(|a, b| b.id.cmp(&a.id));
    Ok(records)
}

pub fn run_exit(run: &RunSnapshot) -> u8 {
    if run.scenarios.iter().any(|s| s.run.error.is_some()) {
        2
    } else if run.scenarios.iter().all(|s| s.passed) {
        0
    } else {
        1
    }
}

pub fn comparison_exit(report: &comparison::ComparisonReport) -> u8 {
    if report.execution_errors {
        2
    } else if report.passed {
        0
    } else if report.inconclusive {
        3
    } else {
        1
    }
}

fn outcome(code: u8) -> String {
    match code {
        0 => "passed",
        1 => "failed",
        3 => "inconclusive",
        _ => "error",
    }
    .into()
}

struct WorkflowLock(PathBuf);
impl WorkflowLock {
    fn acquire(directory: &Path) -> Result<Self, Error> {
        let path = directory.join(".wraith/workflow.lock");
        fs::create_dir_all(path.parent().unwrap())
            .map_err(|e| error::io("create workflow directory", &path, e))?;
        let mut file=fs::OpenOptions::new().write(true).create_new(true).open(&path).map_err(|e|Error::Artifact(format!("Cannot acquire {}: {e}. Another workflow may be running. If a process was forcibly killed, verify it has stopped before removing its stale lock.",path.display())))?;
        let guard = Self(path.clone());
        use std::io::Write;
        writeln!(file, "pid={}", std::process::id())
            .map_err(|e| error::io("write workflow lock", &path, e))?;
        Ok(guard)
    }
}
impl Drop for WorkflowLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

pub struct Options {
    pub samples: Option<u32>,
    pub allow_live: bool,
    pub max_requests: Option<u32>,
    pub replace: bool,
    pub json: bool,
}

pub async fn execute(
    path: &Path,
    is_baseline: bool,
    options: Options,
    cancellation: Cancellation,
) -> Result<u8, Error> {
    let (cfg, directory) = config::load(path)?;
    let directory = fs::canonicalize(&directory)
        .map_err(|e| error::io("resolve project directory", &directory, e))?;
    let settings = project::load(&directory)?;
    let mode = settings
        .as_ref()
        .map(|p| p.mode.as_str())
        .unwrap_or("offline");
    if mode == "live" && !options.allow_live {
        return Err(Error::Config("Live mode needs --allow-live and an explicit request budget. Review the scenarios, then run baseline --allow-live --max-requests N.".into()));
    }
    if mode != "live" && (options.allow_live || options.max_requests.is_some()) {
        return Err(Error::Config(
            "Set mode to live in wraith.project.json before authorizing model requests".into(),
        ));
    }
    if let Some(p) = &settings {
        for name in &p.required_env {
            if std::env::var_os(name).is_none_or(|v| v.is_empty()) {
                return Err(Error::Config(format!(
                    "Missing {name}; run wraith doctor for setup guidance"
                )));
            }
        }
    }
    let _lock = WorkflowLock::acquire(&directory)?;
    let pointer = directory.join(".wraith/baseline.json");
    if is_baseline && pointer.exists() && !options.replace {
        return Err(Error::Config("A baseline already exists. Use check to evaluate your change, or baseline --replace to deliberately refresh it. History is retained.".into()));
    }
    let live_attempt = directory.join(".wraith/live-baseline-attempt.json");
    if is_baseline && mode == "live" && live_attempt.exists() && !options.replace {
        return Err(Error::Config("A live baseline was already attempted. Its reserved requests remain consumed even after failure or interruption. Use baseline --replace --allow-live --max-requests N to deliberately authorize a new experiment. No agent was executed.".into()));
    }
    let previous = if is_baseline {
        None
    } else {
        Some(load_record(&pointer).map_err(|_|Error::Config("No readable baseline. Run wraith baseline first; check never silently creates or replaces it.".into()))?)
    };
    if previous.as_ref().is_some_and(|r| r.kind != "baseline") {
        return Err(Error::Artifact(
            "Baseline pointer must identify a baseline record".into(),
        ));
    }
    let baseline = previous
        .as_ref()
        .map(|record| snapshot::load(&history_path(&directory, &record.id)?.join("run.json")))
        .transpose()?;
    let samples = options
        .samples
        .or_else(|| previous.as_ref().map(|p| p.samples))
        .unwrap_or(1);
    if let Some(b) = &baseline {
        if samples != b.samples_per_scenario
            || cfg.tests.len() != wraith_core::sampling::groups(b).len()
            || cfg
                .tests
                .iter()
                .any(|scenario| !b.scenarios.iter().any(|s| s.scenario == *scenario))
        {
            return Err(Error::Config("Scenario inputs, metadata, expectations, or sample counts changed. Review the suite and run baseline --replace before checking. No agent was executed.".into()));
        }
        if previous.as_ref().is_some_and(|p| p.mode != mode) {
            return Err(Error::Config(
                "Offline/live mode changed; collect a fresh baseline --replace".into(),
            ));
        }
    }
    let id = format!(
        "{}-{}-{}",
        runner::unix_ms(),
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .subsec_nanos()
    );
    let output = history_path(&directory, &id)?;
    let budget_id = if mode == "live" {
        if is_baseline {
            Some(id.clone())
        } else {
            previous.as_ref().and_then(|p| p.budget_id.clone())
        }
    } else {
        None
    };
    let budget = budget_id
        .as_ref()
        .map(|id| history_path(&directory, id).map(|p| p.join("request-budget.json")))
        .transpose()?;
    if mode == "live" {
        if is_baseline {
            let limit=options.max_requests.ok_or_else(||Error::Config("Live baseline needs --max-requests N; one budget covers baseline, checks, failed requests, and retries".into()))?;
            atomic_json(budget.as_ref().unwrap(), &json!({"limit":limit,"used":0}))?;
            // Persist before execution, including attempts that never complete a run.
            atomic_json(&live_attempt, &json!({"version":1,"budgetId":id}))?;
        } else {
            if options.max_requests.is_some() {
                return Err(Error::Config("Check reuses the original budget. --max-requests belongs on baseline; it cannot reset or increase the budget.".into()));
            }
            let value: Value =
                serde_json::from_slice(
                    &fs::read(budget.as_ref().ok_or_else(|| {
                        Error::Config("Live baseline has no request budget".into())
                    })?)
                    .map_err(|e| error::io("read budget", budget.as_ref().unwrap(), e))?,
                )
                .map_err(|e| Error::Config(e.to_string()))?;
            if value["used"]
                .as_u64()
                .zip(value["limit"].as_u64())
                .is_none_or(|(used, limit)| used >= limit)
            {
                return Err(Error::Config(
                    "Request budget exhausted or invalid. No agent was executed.".into(),
                ));
            }
        }
    }
    if !options.json {
        println!(
            "{}: {} scenarios × {samples} samples. Mode: {mode}.",
            if is_baseline { "Baseline" } else { "Check" },
            cfg.tests.len()
        );
        if let Some(p) = &budget {
            println!("Shared request budget: {}", p.display());
        }
    }
    let run = runner::run_with_options(
        &cfg,
        &directory,
        None,
        &runner::RunOptions {
            samples,
            cancellation: cancellation.clone(),
            request_budget: budget.clone(),
        },
    )
    .await?;
    if cancellation.is_cancelled() {
        return Err(Error::Cancelled);
    }
    fs::create_dir_all(&output).map_err(|e| error::io("create history", &output, e))?;
    snapshot::save(&output.join("run.json"), &run)?;
    let budgeted = mode != "live"
        || run
            .scenarios
            .iter()
            .filter_map(|s| s.run.response.as_ref())
            .all(|r| {
                r.metadata
                    .get("wraith")
                    .is_some_and(|v| v["budgeted"] == true && v["modelCalls"].as_u64().is_some())
            });
    let comparison = baseline
        .as_ref()
        .map(|b| comparison::compare_with_policy(b, &run, Some(&cfg)))
        .transpose()?;
    let code = if !budgeted {
        2
    } else if let Some(report) = &comparison {
        comparison_exit(report)
    } else {
        run_exit(&run)
    };
    let record = Record {
        version: 1,
        id: id.clone(),
        kind: if is_baseline { "baseline" } else { "check" }.into(),
        baseline_id: previous.as_ref().map(|p| p.id.clone()),
        created_at_unix_ms: run.created_at_unix_ms,
        samples,
        mode: mode.into(),
        model: settings.as_ref().and_then(|p| p.model.clone()),
        agent_command: cfg.agent.command.clone(),
        git_commit: git(&directory, &["rev-parse", "HEAD"]),
        git_dirty: git(&directory, &["status", "--porcelain"]).is_some_and(|s| !s.is_empty()),
        outcome: outcome(code),
        budget_id,
    };
    if let Some(report) = &comparison {
        atomic_json(&output.join("comparison.json"), report)?;
    }
    atomic_json(&output.join("record.json"), &record)?;
    report::save(
        &output.join("report.html"),
        &run,
        baseline.as_ref(),
        comparison.as_ref(),
        Some(&record),
    )?;
    if is_baseline {
        if run.scenarios.iter().any(|s| s.run.error.is_some()) || !budgeted {
            if !options.json {
                eprintln!(
                    "Baseline has execution/instrumentation errors; it was retained in history but not accepted. Fix the adapter and rerun baseline; live attempts require --replace to authorize a new budget."
                );
            }
        } else {
            atomic_json(&pointer, &record)?;
        }
    } else {
        atomic_json(&directory.join(".wraith/latest-check.json"), &record)?;
    }
    report::index(&directory, &history(&directory)?)?;
    if options.json {
        println!("{}",serde_json::to_string_pretty(&json!({"record":record,"run":run,"comparison":comparison,"report":output.join("report.html"),"requestBudget":budget.as_ref().map(|p|fs::read_to_string(p).ok().and_then(|s|serde_json::from_str::<Value>(&s).ok()))})).map_err(|e|Error::Artifact(e.to_string()))?);
    } else {
        if let Some(report) = &comparison {
            render::comparison("baseline", "current agent", report);
        } else {
            render::run(&run);
        }
        if !budgeted {
            eprintln!(
                "Live adapter did not report budgeted model calls. Use the supplied SDK model-call helper for every attempt; arbitrary agent network calls cannot be capped by Wraith."
            );
        }
        println!(
            "Report: {}\nHistory: {}",
            output.join("report.html").display(),
            directory.join(".wraith/index.html").display()
        );
    }
    Ok(code)
}

pub fn render_saved(
    path: &Path,
    id: Option<&str>,
    destination: Option<&Path>,
) -> Result<PathBuf, Error> {
    let directory = project::directory(path);
    let records = history(directory)?;
    if let Some(id) = id {
        let output = history_path(directory, id)?;
        let record = load_record(&output.join("record.json"))?;
        let run = snapshot::load(&output.join("run.json"))?;
        let baseline = record
            .baseline_id
            .as_ref()
            .map(|id| snapshot::load(&history_path(directory, id)?.join("run.json")))
            .transpose()?;
        let comparison_path = output.join("comparison.json");
        let comparison: Option<Value> = if comparison_path.exists() {
            Some(
                serde_json::from_slice(
                    &fs::read(&comparison_path)
                        .map_err(|e| error::io("read comparison", &comparison_path, e))?,
                )
                .map_err(|e| Error::Artifact(e.to_string()))?,
            )
        } else {
            None
        };
        let destination = destination
            .map(Path::to_path_buf)
            .unwrap_or_else(|| output.join("report.html"));
        report::save_value(
            &destination,
            &run,
            baseline.as_ref(),
            comparison.as_ref(),
            Some(&record),
        )?;
        Ok(destination)
    } else {
        report::index(directory, &records)?;
        if let Some(destination) = destination {
            fs::copy(directory.join(".wraith/index.html"), destination)
                .map_err(|e| error::io("copy history report", destination, e))?;
            return Ok(destination.to_path_buf());
        }
        Ok(directory.join(".wraith/index.html"))
    }
}
