use std::process::{Command, Output};

fn cli(dir: &std::path::Path, args: &[&str], candidate: bool) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_wraith"));
    command
        .current_dir(dir)
        .args(args)
        .env_remove("WRAITH_EXAMPLE_MODE");
    if candidate {
        command.env("WRAITH_EXAMPLE_MODE", "candidate");
    }
    command.output().unwrap()
}

#[test]
fn init_run_save_compare_and_json_exit_contract() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init"], false).status.success());
    let original = std::fs::read(dir.path().join("wraith.yaml")).unwrap();
    assert_eq!(cli(dir.path(), &["init"], false).status.code(), Some(2));
    assert_eq!(
        std::fs::read(dir.path().join("wraith.yaml")).unwrap(),
        original
    );
    let baseline = cli(
        dir.path(),
        &["run", "--save", "baseline", "--output", "json"],
        false,
    );
    assert!(
        baseline.status.success(),
        "{}",
        String::from_utf8_lossy(&baseline.stderr)
    );
    let json: serde_json::Value = serde_json::from_slice(&baseline.stdout).unwrap();
    assert_eq!(json["scenarios"].as_array().unwrap().len(), 3);
    let candidate = cli(dir.path(), &["run", "--save", "candidate"], true);
    assert_eq!(candidate.status.code(), Some(1));
    let report = cli(
        dir.path(),
        &["compare", "baseline", "candidate", "--output", "json"],
        false,
    );
    assert_eq!(report.status.code(), Some(1));
    let json: serde_json::Value = serde_json::from_slice(&report.stdout).unwrap();
    assert!(
        json["changes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c["classification"] == "TOOL_SELECTION_REGRESSION")
    );
    assert!(
        cli(dir.path(), &["compare", "baseline", "baseline"], false)
            .status
            .success()
    );
    assert!(
        cli(
            dir.path(),
            &["compare", "baseline", ".wraith/runs/baseline.json"],
            false
        )
        .status
        .success()
    );
    assert_eq!(
        cli(dir.path(), &["run", "--scenario", "missing"], false)
            .status
            .code(),
        Some(2)
    );
    assert_eq!(
        cli(dir.path(), &["run", "--save", "../escape"], false)
            .status
            .code(),
        Some(2)
    );
    let filtered = cli(
        dir.path(),
        &["run", "--scenario", "find-pto-policy", "--output", "json"],
        false,
    );
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&filtered.stdout).unwrap()["scenarios"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    // Saved comparisons remain usable after the config is removed.
    std::fs::remove_file(dir.path().join("wraith.yaml")).unwrap();
    assert!(
        cli(dir.path(), &["compare", "baseline", "baseline"], false)
            .status
            .success()
    );
}

#[test]
fn execution_failure_is_two_and_failed_run_is_still_saved() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(
        dir.path().join("wraith.yaml"),
        "version: 1\nagent: {command: nonexistent-wraith-agent}\ntests:\n- id: test\n  input: hi\n",
    )
    .unwrap();
    let output = cli(
        dir.path(),
        &["run", "--save", "broken", "--output", "json"],
        false,
    );
    assert_eq!(output.status.code(), Some(2));
    assert!(serde_json::from_slice::<serde_json::Value>(&output.stdout).is_ok());
    assert!(dir.path().join(".wraith/runs/broken.json").exists());
    assert_eq!(
        cli(dir.path(), &["compare", "broken", "broken"], false)
            .status
            .code(),
        Some(2)
    );
}

#[test]
fn sampled_cli_schema_and_policy_override() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init"], false).status.success());
    let result = cli(
        dir.path(),
        &[
            "run",
            "--samples",
            "3",
            "--save",
            "baseline",
            "--output",
            "json",
        ],
        false,
    );
    assert!(result.status.success());
    let value: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(value["schemaVersion"], 3);
    assert_eq!(value["samplesPerScenario"], 3);
    assert_eq!(value["scenarios"].as_array().unwrap().len(), 9);
    assert_eq!(
        cli(
            dir.path(),
            &["run", "--samples", "3", "--save", "candidate"],
            true
        )
        .status
        .code(),
        Some(1)
    );
    let report = cli(
        dir.path(),
        &[
            "compare",
            "baseline",
            "candidate",
            "--policy",
            "wraith.yaml",
            "--output",
            "json",
        ],
        false,
    );
    assert_eq!(report.status.code(), Some(1));
    let value: serde_json::Value = serde_json::from_slice(&report.stdout).unwrap();
    assert_eq!(value["scenarioSampling"][1]["baseline"]["count"], 3);
    assert_eq!(
        cli(dir.path(), &["run", "--samples", "0"], false)
            .status
            .code(),
        Some(2)
    );
}

#[cfg(unix)]
#[test]
fn ctrl_c_cleans_up_and_preserves_existing_snapshot() {
    use std::time::{Duration, Instant};
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"), r#"
import json, sys, subprocess, pathlib, time
json.loads(sys.stdin.readline())
subprocess.Popen([sys.executable, '-c', "import pathlib,time; time.sleep(2); pathlib.Path('orphan').write_text('alive')"])
pathlib.Path('ready').write_text('ready')
time.sleep(10)
"#).unwrap();
    std::fs::write(dir.path().join("wraith.yaml"), "version: 1\nagent: {command: 'python3 agent.py', timeout_ms: 20000}\ntests:\n- id: interrupt\n  input: hi\n").unwrap();
    let runs = dir.path().join(".wraith/runs");
    std::fs::create_dir_all(&runs).unwrap();
    let previous = runs.join("baseline.json");
    std::fs::write(&previous, "preserve existing run").unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_wraith"))
        .current_dir(dir.path())
        .args(["run", "--save", "baseline"])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    while !dir.path().join("ready").exists() {
        if Instant::now() > deadline {
            let _ = child.kill();
            panic!("agent did not start");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    assert!(
        Command::new("python3")
            .args([
                "-c",
                "import os,signal,sys; os.kill(int(sys.argv[1]), signal.SIGINT)",
                &child.id().to_string()
            ])
            .status()
            .unwrap()
            .success()
    );
    let deadline = Instant::now() + Duration::from_secs(5);
    let status = loop {
        if let Some(status) = child.try_wait().unwrap() {
            break status;
        }
        if Instant::now() > deadline {
            let _ = child.kill();
            panic!("Ctrl-C did not finish cleanup");
        }
        std::thread::sleep(Duration::from_millis(10));
    };
    assert_eq!(status.code(), Some(130));
    assert_eq!(
        std::fs::read_to_string(previous).unwrap(),
        "preserve existing run"
    );
    std::thread::sleep(Duration::from_millis(2200));
    assert!(!dir.path().join("orphan").exists());
}

#[test]
fn inconclusive_is_exit_three_in_human_and_json_reports() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init"], false).status.success());
    let path = dir.path().join("wraith.yaml");
    let text = std::fs::read_to_string(&path).unwrap();
    std::fs::write(&path, format!("{text}\ncomparison:\n  statistical:\n    min_samples: 20\n    max_failure_rate_increase_pp: 10\n    alpha: 0.05\n")).unwrap();
    for name in ["baseline", "candidate"] {
        assert!(
            cli(
                dir.path(),
                &["run", "--samples", "2", "--save", name],
                false
            )
            .status
            .success()
        );
    }
    let result = cli(
        dir.path(),
        &["compare", "baseline", "candidate", "--output", "json"],
        false,
    );
    assert_eq!(result.status.code(), Some(3));
    let report: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["passed"], false);
    assert_eq!(report["inconclusive"], true);
    let human = cli(dir.path(), &["compare", "baseline", "candidate"], false);
    assert_eq!(human.status.code(), Some(3));
    assert!(
        String::from_utf8(human.stdout)
            .unwrap()
            .contains("INCONCLUSIVE")
    );
}
