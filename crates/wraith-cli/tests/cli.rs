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
    assert_eq!(value["schemaVersion"], 4);
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

#[test]
fn baseline_check_history_and_preflight_preserve_evidence() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init", "--demo"], false).status.success());
    assert!(cli(dir.path(), &["doctor"], false).status.success());
    assert!(cli(dir.path(), &["baseline"], false).status.success());
    let pointer = dir.path().join(".wraith/baseline.json");
    let original = std::fs::read(&pointer).unwrap();
    assert_eq!(cli(dir.path(), &["baseline"], false).status.code(), Some(2));
    assert_eq!(std::fs::read(&pointer).unwrap(), original);
    let check = cli(dir.path(), &["check", "--output", "json"], true);
    assert_eq!(
        check.status.code(),
        Some(1),
        "{}",
        String::from_utf8_lossy(&check.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&check.stdout).unwrap();
    assert_eq!(result["record"]["outcome"], "failed");
    let html = std::fs::read_to_string(result["report"].as_str().unwrap()).unwrap();
    assert!(html.contains("TOOL_SELECTION_REGRESSION"));
    assert!(html.contains("Final output"));
    assert_eq!(std::fs::read(&pointer).unwrap(), original);
    let history = cli(dir.path(), &["history", "--output", "json"], false);
    let records: serde_json::Value = serde_json::from_slice(&history.stdout).unwrap();
    assert_eq!(records.as_array().unwrap().len(), 2);
    let config = dir.path().join("wraith.yaml");
    let changed = std::fs::read_to_string(&config)
        .unwrap()
        .replace("20 PTO days?", "21 PTO days?");
    // Change a known input reliably, leaving expectations intact.
    std::fs::write(
        &config,
        changed.replace(
            "How many PTO days do employees receive?",
            "How many holidays do employees receive?",
        ),
    )
    .unwrap();
    let check = cli(dir.path(), &["check"], false);
    assert_eq!(check.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&check.stderr).contains("No agent was executed"));
    assert_eq!(std::fs::read(&pointer).unwrap(), original);
}

#[test]
fn live_function_adapter_budget_and_opt_in_fail_closed() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"),"def evaluate(input, context):\n    with context.model_call():\n        return {'text':'ok'}\n").unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--language",
                "python",
                "--mode",
                "live"
            ],
            false
        )
        .status
        .success()
    );
    assert_eq!(cli(dir.path(), &["baseline"], false).status.code(), Some(2));
    assert!(!dir.path().join(".wraith/history").exists());
    assert!(
        cli(
            dir.path(),
            &["baseline", "--allow-live", "--max-requests", "2"],
            false
        )
        .status
        .success()
    );
    assert_eq!(cli(dir.path(), &["check"], false).status.code(), Some(2));
    assert!(
        cli(dir.path(), &["check", "--allow-live"], false)
            .status
            .success()
    );
    let result = cli(dir.path(), &["check", "--allow-live"], false);
    assert_eq!(result.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&result.stderr).contains("exhausted"));
    let pointer: serde_json::Value =
        serde_json::from_slice(&std::fs::read(dir.path().join(".wraith/baseline.json")).unwrap())
            .unwrap();
    let budget = dir
        .path()
        .join(".wraith/history")
        .join(pointer["id"].as_str().unwrap())
        .join("request-budget.json");
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&std::fs::read(budget).unwrap()).unwrap()["used"],
        2
    );
}

#[test]
fn failed_live_baseline_cannot_silently_reset_its_budget() {
    let dir = tempfile::tempdir().unwrap();
    let agent = dir.path().join("agent.py");
    std::fs::write(&agent, "def evaluate(input, context):\n    with context.model_call():\n        raise RuntimeError('provider failed')\n").unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--mode",
                "live"
            ],
            false
        )
        .status
        .success()
    );
    let args = ["baseline", "--allow-live", "--max-requests", "2"];
    assert_eq!(cli(dir.path(), &args, false).status.code(), Some(2));
    assert!(!dir.path().join(".wraith/baseline.json").exists());
    let attempt_path = dir.path().join(".wraith/live-baseline-attempt.json");
    let attempt = std::fs::read(&attempt_path).unwrap();
    let value: serde_json::Value = serde_json::from_slice(&attempt).unwrap();
    let budget_path = dir
        .path()
        .join(".wraith/history")
        .join(value["budgetId"].as_str().unwrap())
        .join("request-budget.json");
    let budget = std::fs::read(&budget_path).unwrap();
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&budget).unwrap()["used"],
        1
    );
    std::fs::write(&agent, "def evaluate(input, context):\n    with context.model_call():\n        return {'text':'ok'}\n").unwrap();
    let blocked = cli(dir.path(), &args, false);
    assert_eq!(blocked.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&blocked.stderr).contains("No agent was executed"));
    assert_eq!(std::fs::read(&attempt_path).unwrap(), attempt);
    assert_eq!(std::fs::read(&budget_path).unwrap(), budget);
    assert!(
        cli(
            dir.path(),
            &[
                "baseline",
                "--replace",
                "--allow-live",
                "--max-requests",
                "2"
            ],
            false
        )
        .status
        .success()
    );
    assert_ne!(std::fs::read(attempt_path).unwrap(), attempt);
    assert_eq!(std::fs::read(budget_path).unwrap(), budget);
}

#[test]
fn generated_adapter_handles_async_logs_and_escapes_html() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("agent.py"),"print('import log')\nasync def evaluate(input, context):\n    print('runtime log')\n    context.tool('lookup', {'q':'hello'}, 'found')\n    return {'text':'<script>alert(1)</script>'}\n").unwrap();
    assert!(
        cli(
            dir.path(),
            &[
                "init",
                "--entrypoint",
                "agent.py:evaluate",
                "--language",
                "python",
                "--template",
                "tools"
            ],
            false
        )
        .status
        .success()
    );
    let baseline = cli(dir.path(), &["baseline", "--output", "json"], false);
    assert!(
        baseline.status.success(),
        "{}",
        String::from_utf8_lossy(&baseline.stderr)
    );
    let result: serde_json::Value = serde_json::from_slice(&baseline.stdout).unwrap();
    let html = std::fs::read_to_string(result["report"].as_str().unwrap()).unwrap();
    assert!(!html.contains("<script>"));
    assert!(html.contains("&lt;script&gt;"));
    assert_eq!(
        result["run"]["scenarios"][0]["run"]["response"]["toolCalls"][0]["name"],
        "lookup"
    );
}

#[test]
fn import_reviewed_case_and_ci_bootstrap_are_reviewable() {
    let dir = tempfile::tempdir().unwrap();
    assert!(cli(dir.path(), &["init", "--demo"], false).status.success());
    std::fs::write(
        dir.path().join("input.json"),
        r#"{"text":"reported request"}"#,
    )
    .unwrap();
    std::fs::write(
        dir.path().join("expect.json"),
        r#"{"output_contains":["correct"]}"#,
    )
    .unwrap();
    let args = [
        "cases",
        "add",
        "--id",
        "reported-bug",
        "--input",
        "input.json",
        "--expect",
        "expect.json",
    ];
    let imported = cli(dir.path(), &args, false);
    assert!(
        imported.status.success(),
        "{}",
        String::from_utf8_lossy(&imported.stderr)
    );
    let config = dir.path().join("wraith.yaml");
    let bytes = std::fs::read(&config).unwrap();
    let suite: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(suite["tests"].as_array().unwrap().len(), 4);
    assert_eq!(cli(dir.path(), &args, false).status.code(), Some(2));
    assert_eq!(std::fs::read(&config).unwrap(), bytes);
    assert!(
        Command::new("git")
            .args(["init", "--quiet"])
            .current_dir(dir.path())
            .status()
            .unwrap()
            .success()
    );
    let generated = cli(dir.path(), &["ci", "init"], false);
    assert!(
        generated.status.success(),
        "{}",
        String::from_utf8_lossy(&generated.stderr)
    );
    let workflow = dir.path().join(".github/workflows/wraith.yml");
    let original = std::fs::read(&workflow).unwrap();
    let yaml = String::from_utf8(original.clone()).unwrap();
    assert!(yaml.contains("github.event.pull_request.base.sha"));
    assert!(yaml.contains("wraith-evidence"));
    assert!(!yaml.contains("__CONFIG_JSON__"));
    assert_eq!(
        cli(dir.path(), &["ci", "init"], false).status.code(),
        Some(2)
    );
    assert_eq!(std::fs::read(workflow).unwrap(), original);
}
