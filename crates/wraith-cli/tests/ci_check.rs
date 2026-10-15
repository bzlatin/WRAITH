use serde_json::{Value, json};
use std::{
    path::Path,
    process::{Command, Output},
};

fn cli(directory: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_wraith"))
        .current_dir(directory)
        .args(args)
        .output()
        .unwrap()
}
fn setup(root: &Path) {
    std::fs::create_dir_all(root).unwrap();
    std::fs::write(
        root.join("agent.py"),
        r#"
import json, pathlib, sys
r=json.loads(sys.stdin.readline())
pathlib.Path('executed').write_text('yes')
answer=pathlib.Path('answer').read_text()
print(json.dumps({'protocolVersion':1,'scenarioId':r['scenarioId'],'output':{'text':answer}}))
"#,
    )
    .unwrap();
    std::fs::write(root.join("answer"), "APPROVED").unwrap();
    let python = if cfg!(windows) { "python" } else { "python3" };
    std::fs::write(root.join("wraith.yaml"),json!({"version":1,"agent":{"command":format!("{python} agent.py")},"tests":[{"id":"<script> [click](https://example.invalid)","input":{},"expect":{"output_contains":["APPROVED"]}}]}).to_string()).unwrap();
}
fn check(candidate: &Path, base: &Path, output: &Path) -> Output {
    cli(
        candidate,
        &[
            "ci",
            "check",
            "--base-config",
            base.join("wraith.yaml").to_str().unwrap(),
            "--artifacts",
            output.to_str().unwrap(),
            "--jobs",
            "2",
            "--output",
            "json",
        ],
    )
}

#[test]
fn ci_uses_base_policy_and_writes_escaped_actionable_evidence_without_overwrite() {
    let dir = tempfile::tempdir().unwrap();
    let base = dir.path().join("base");
    let candidate = dir.path().join("candidate");
    setup(&base);
    setup(&candidate);
    let output = dir.path().join("evidence");
    let pass = check(&candidate, &base, &output);
    assert!(
        pass.status.success(),
        "{}",
        String::from_utf8_lossy(&pass.stderr)
    );
    let saved = std::fs::read(output.join("ci.json")).unwrap();
    let value: Value = serde_json::from_slice(&saved).unwrap();
    assert_eq!(value["exitCode"], 0);
    assert_eq!(value["candidateExecuted"], true);
    assert_eq!(check(&candidate, &base, &output).status.code(), Some(2));
    assert_eq!(std::fs::read(output.join("ci.json")).unwrap(), saved);
    std::fs::write(
        candidate.join("answer"),
        "<script>alert('x')</script> [bad](https://example.invalid)",
    )
    .unwrap();
    // The PR's policy cannot make its output pass or replace the adapter command.
    std::fs::write(
        candidate.join("wraith.yaml"),
        "untrusted: invalid candidate policy",
    )
    .unwrap();
    let failed = dir.path().join("failed");
    let result = check(&candidate, &base, &failed);
    assert_eq!(
        result.status.code(),
        Some(1),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let value: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(value["comparison"]["passed"], false);
    let summary = std::fs::read_to_string(failed.join("summary.md")).unwrap();
    assert!(summary.contains("&lt;script&gt;"));
    assert!(!summary.contains("<script>"));
    assert!(!summary.contains("[click](https://example.invalid)"));
    assert!(summary.contains("Baseline") && summary.contains("Candidate"));
    assert!(failed.join("report.html").exists());
}

#[test]
fn ci_stops_on_red_or_broken_baseline_and_rejects_declared_live_before_execution() {
    let dir = tempfile::tempdir().unwrap();
    let base = dir.path().join("base");
    let candidate = dir.path().join("candidate");
    setup(&base);
    setup(&candidate);
    std::fs::write(base.join("answer"), "DENIED").unwrap();
    let output = dir.path().join("red");
    let result = check(&candidate, &base, &output);
    assert_eq!(result.status.code(), Some(1));
    assert!(!candidate.join("executed").exists());
    let record: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(record["candidateExecuted"], false);
    assert_eq!(record["comparison"], Value::Null);
    assert!(!output.join("candidate.json").exists());
    std::fs::remove_file(base.join("agent.py")).unwrap();
    let broken = check(&candidate, &base, &dir.path().join("broken"));
    assert_eq!(broken.status.code(), Some(2));
    assert!(!candidate.join("executed").exists());
    std::fs::write(base.join("wraith.project.json"),json!({"version":1,"language":"python","entrypoint":"agent.py:evaluate","mode":"live","model":null,"requiredEnv":[]}).to_string()).unwrap();
    assert_eq!(
        check(&candidate, &base, &dir.path().join("live"))
            .status
            .code(),
        Some(2)
    );
    assert!(!dir.path().join("live").exists());
}

#[test]
fn ci_preserves_inconclusive_exit_and_appends_summary() {
    let dir = tempfile::tempdir().unwrap();
    let base = dir.path().join("base");
    let candidate = dir.path().join("candidate");
    setup(&base);
    setup(&candidate);
    let mut config: Value =
        serde_json::from_slice(&std::fs::read(base.join("wraith.yaml")).unwrap()).unwrap();
    config["comparison"] =
        json!({"statistical":{"min_samples":20,"max_failure_rate_increase_pp":10,"alpha":0.05}});
    std::fs::write(base.join("wraith.yaml"), config.to_string()).unwrap();
    let summary = dir.path().join("job-summary.md");
    std::fs::write(&summary, "Earlier step\n\n").unwrap();
    let result = cli(
        &candidate,
        &[
            "ci",
            "check",
            "--base-config",
            base.join("wraith.yaml").to_str().unwrap(),
            "--summary",
            summary.to_str().unwrap(),
            "--artifacts",
            dir.path().join("uncertain").to_str().unwrap(),
        ],
    );
    assert_eq!(
        result.status.code(),
        Some(3),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let text = std::fs::read_to_string(summary).unwrap();
    assert!(text.starts_with("Earlier step\n\n"));
    assert!(text.contains("Inconclusive"));
}

#[test]
fn live_parallel_flags_and_summary_aliases_fail_before_execution() {
    let dir = tempfile::tempdir().unwrap();
    let base = dir.path().join("base");
    let candidate = dir.path().join("candidate");
    setup(&base);
    setup(&candidate);
    let output = dir.path().join("bad-summary");
    let result = cli(
        &candidate,
        &[
            "ci",
            "check",
            "--base-config",
            base.join("wraith.yaml").to_str().unwrap(),
            "--artifacts",
            output.to_str().unwrap(),
            "--summary",
            output.join("baseline.json").to_str().unwrap(),
        ],
    );
    assert_eq!(result.status.code(), Some(2));
    assert!(!base.join("executed").exists());
    assert!(!output.join("baseline.json").exists());
    std::fs::write(candidate.join("wraith.project.json"),json!({"version":1,"language":"protocol","entrypoint":"agent.py","mode":"live","model":null,"requiredEnv":[]}).to_string()).unwrap();
    for command in [
        vec!["run", "--jobs", "2"],
        vec![
            "baseline",
            "--jobs",
            "2",
            "--allow-live",
            "--max-requests",
            "10",
        ],
    ] {
        assert_eq!(cli(&candidate, &command).status.code(), Some(2));
    }
    assert!(!candidate.join("executed").exists());
    assert!(!candidate.join(".wraith").exists());
}

#[cfg(unix)]
#[test]
fn interrupted_ci_has_no_completed_record_or_partial_candidate_snapshot() {
    use std::time::{Duration, Instant};
    let dir = tempfile::tempdir().unwrap();
    let base = dir.path().join("base");
    let candidate = dir.path().join("candidate");
    setup(&base);
    setup(&candidate);
    std::fs::write(
        candidate.join("agent.py"),
        "import pathlib,time; pathlib.Path('ready').write_text('ready'); time.sleep(20)",
    )
    .unwrap();
    let output = dir.path().join("interrupted");
    let mut child = Command::new(env!("CARGO_BIN_EXE_wraith"))
        .current_dir(&candidate)
        .args([
            "ci",
            "check",
            "--base-config",
            base.join("wraith.yaml").to_str().unwrap(),
            "--jobs",
            "2",
            "--samples",
            "2",
            "--artifacts",
            output.to_str().unwrap(),
        ])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(8);
    while !candidate.join("ready").exists() {
        if Instant::now() > deadline {
            let _ = child.kill();
            panic!("candidate did not start");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    assert!(
        Command::new("python3")
            .args([
                "-c",
                "import os,signal,sys; os.kill(int(sys.argv[1]),signal.SIGINT)",
                &child.id().to_string()
            ])
            .status()
            .unwrap()
            .success()
    );
    let deadline = Instant::now() + Duration::from_secs(8);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            panic!("CI did not stop");
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    assert_eq!(status.code(), Some(130));
    assert!(output.join("baseline.json").exists());
    assert!(!output.join("candidate.json").exists());
    assert!(!output.join("ci.json").exists());
}

#[test]
fn checks_inherit_baseline_jobs_and_reject_changed_or_future_execution_metadata() {
    let dir = tempfile::tempdir().unwrap();
    setup(dir.path());
    let baseline = cli(dir.path(), &["baseline", "--jobs", "2", "--output", "json"]);
    assert!(
        baseline.status.success(),
        "{}",
        String::from_utf8_lossy(&baseline.stderr)
    );
    let value: Value = serde_json::from_slice(&baseline.stdout).unwrap();
    assert_eq!(value["record"]["version"], 2);
    assert_eq!(value["record"]["jobs"], 2);
    assert!(cli(dir.path(), &["check"]).status.success());
    std::fs::remove_file(dir.path().join("executed")).unwrap();
    assert_eq!(
        cli(dir.path(), &["check", "--jobs", "1"]).status.code(),
        Some(2)
    );
    assert!(!dir.path().join("executed").exists());
    let pointer = dir.path().join(".wraith/baseline.json");
    let mut future = value["record"].clone();
    future["version"] = 3.into();
    std::fs::write(&pointer, future.to_string()).unwrap();
    let result = cli(dir.path(), &["check"]);
    assert_eq!(result.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&result.stderr).contains("upgrade Wraith"));
    assert!(!dir.path().join("executed").exists());
    // Build an actual sequential baseline, then migrate its record in memory.
    assert!(
        cli(dir.path(), &["baseline", "--replace", "--jobs", "1"])
            .status
            .success()
    );
    let bytes = std::fs::read(&pointer).unwrap();
    let mut legacy: Value = serde_json::from_slice(&bytes).unwrap();
    legacy["version"] = 1.into();
    legacy.as_object_mut().unwrap().remove("jobs");
    std::fs::write(&pointer, legacy.to_string()).unwrap();
    let before = std::fs::read(&pointer).unwrap();
    assert!(cli(dir.path(), &["check"]).status.success());
    assert_eq!(
        std::fs::read(&pointer).unwrap(),
        before,
        "migration must not rewrite old records"
    );
}
